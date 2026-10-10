"""Authenticated provisioning and mapping endpoints for opt-in Matrix E2EE."""
from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from auth_users.authentication import SessionJWTAuthentication as JWTAuthentication

from ..matrix_service import (
    MatrixServiceError,
    create_device_session,
    ensure_matrix_identity,
    matrix_is_configured,
    matrix_request,
    revoke_device,
    verify_encrypted_room_binding,
)
from ..models import Conversation, ConversationParticipant, MatrixDevice, MatrixIdentity
from ..serializers import ConversationDetailSerializer, build_conversation_list_context
from ..utils import users_blocked
from .common import err, ok

logger = logging.getLogger("messenger.matrix.api")
User = get_user_model()


def _matrix_token(request):
    # Deliberately use a separate header so the Django JWT authenticator never
    # interprets a Matrix access token as a Paas Deployer session.
    return (request.headers.get("X-Matrix-Access-Token") or "").strip()


def _service_error_response(exc: MatrixServiceError):
    return err(str(exc), exc.status_code)


class MatrixDeviceSessionAPIView(APIView):
    """Create/login a real Matrix device while keeping admin credentials server-side."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not matrix_is_configured():
            return err("Secure chat is not configured on this deployment.", status.HTTP_503_SERVICE_UNAVAILABLE)
        device_id = request.data.get("device_id")
        display_name = request.data.get("display_name") or "Paas Deployer browser"
        try:
            session = create_device_session(request.user, device_id, display_name)
        except MatrixServiceError as exc:
            return _service_error_response(exc)
        except Exception:
            logger.exception("Unexpected Matrix device-session error for django_user_id=%s", request.user.pk)
            return err("Could not start a secure-chat device session.", status.HTTP_503_SERVICE_UNAVAILABLE)
        return ok("Matrix device session ready", data=session, http_status=status.HTTP_201_CREATED)


class MatrixIdentityResolveAPIView(APIView):
    """Return server-created Matrix IDs for approved Messenger invitees only."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not matrix_is_configured():
            return err("Secure chat is not configured on this deployment.", status.HTTP_503_SERVICE_UNAVAILABLE)
        raw_ids = request.data.get("user_ids")
        if not isinstance(raw_ids, list) or len(raw_ids) > 100:
            return err("user_ids must be a list containing at most 100 users.", status.HTTP_400_BAD_REQUEST)
        normalized = []
        for value in raw_ids:
            if isinstance(value, bool):
                return err("Every user_id must be an integer.", status.HTTP_400_BAD_REQUEST)
            try:
                user_id = int(value)
            except (TypeError, ValueError):
                return err("Every user_id must be an integer.", status.HTTP_400_BAD_REQUEST)
            if user_id <= 0:
                return err("Every user_id must be a positive integer.", status.HTTP_400_BAD_REQUEST)
            if user_id not in normalized:
                normalized.append(user_id)
        if request.user.pk not in normalized:
            normalized.append(request.user.pk)
        users = list(User.objects.filter(pk__in=normalized, is_active=True).order_by("pk"))
        if {user.pk for user in users} != set(normalized):
            return err("One or more requested users do not exist or are inactive.", status.HTTP_400_BAD_REQUEST)
        for target in users:
            if target.pk != request.user.pk and users_blocked(request.user, target):
                return err("A secure room cannot be created with a blocked user.", status.HTTP_403_FORBIDDEN)
        output = []
        try:
            for target in users:
                identity, _password = ensure_matrix_identity(target)
                output.append({"user_id": target.pk, "matrix_user_id": identity.matrix_user_id})
        except MatrixServiceError as exc:
            return _service_error_response(exc)
        except Exception:
            logger.exception("Unexpected Matrix identity resolution failure for requester=%s", request.user.pk)
            return err("Matrix identities could not be prepared.", status.HTTP_503_SERVICE_UNAVAILABLE)
        return ok(data={"users": output})


class MatrixDeviceListAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        devices = MatrixDevice.objects.filter(user=request.user).order_by("-last_seen_at")
        return ok(data={"results": [
            {
                "device_id": device.device_id,
                "display_name": device.display_name,
                "created_at": device.created_at.isoformat(),
                "last_seen_at": device.last_seen_at.isoformat(),
                "revoked_at": device.revoked_at.isoformat() if device.revoked_at else None,
                "is_current": device.device_id == (
                    (request.headers.get("X-Matrix-Device-ID") or "").strip()
                ),
            }
            for device in devices
        ]})


class MatrixDeviceRevokeAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, device_id):
        if not matrix_is_configured():
            return err("Secure chat is not configured on this deployment.", status.HTTP_503_SERVICE_UNAVAILABLE)
        try:
            revoke_device(request.user, device_id)
        except MatrixServiceError as exc:
            return _service_error_response(exc)
        except Exception:
            logger.exception("Unexpected Matrix device revocation failure for user_id=%s", request.user.pk)
            return err("Could not revoke the Matrix device.", status.HTTP_503_SERVICE_UNAVAILABLE)
        return ok("Matrix device revoked", data={"device_id": device_id})


class SecureConversationMapAPIView(APIView):
    """Bind an already-created Matrix E2EE room to a Messenger conversation.

    The room and encryption are created by the official Matrix SDK in the
    browser. This endpoint verifies the token, device, encryption algorithm,
    participant membership and (for group roots) Space relation before saving
    any Django metadata. It never creates a plaintext fallback.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not matrix_is_configured():
            return err("Secure chat is not configured on this deployment.", status.HTTP_503_SERVICE_UNAVAILABLE)
        access_token = _matrix_token(request)
        if not access_token:
            return err("A Matrix device session is required.", status.HTTP_401_UNAUTHORIZED)

        room_id = request.data.get("room_id")
        space_id = request.data.get("space_id") or None
        ctype = str(request.data.get("type") or "private").lower()
        if ctype not in (Conversation.Type.PRIVATE, Conversation.Type.GROUP):
            return err("Unsupported conversation type.", status.HTTP_400_BAD_REQUEST)
        raw_ids = request.data.get("member_ids") or []
        if not isinstance(raw_ids, list) or len(raw_ids) > 100:
            return err("member_ids must be a list containing at most 100 users.", status.HTTP_400_BAD_REQUEST)
        ids = []
        for value in raw_ids:
            if isinstance(value, bool):
                return err("Every member_id must be an integer.", status.HTTP_400_BAD_REQUEST)
            try:
                value = int(value)
            except (TypeError, ValueError):
                return err("Every member_id must be an integer.", status.HTTP_400_BAD_REQUEST)
            if value <= 0:
                return err("Every member_id must be positive.", status.HTTP_400_BAD_REQUEST)
            if value not in ids:
                ids.append(value)
        if request.user.pk not in ids:
            ids.append(request.user.pk)
        users = list(User.objects.filter(pk__in=ids, is_active=True).order_by("pk"))
        if {u.pk for u in users} != set(ids):
            return err("One or more conversation members do not exist or are inactive.", status.HTTP_400_BAD_REQUEST)
        if ctype == Conversation.Type.PRIVATE and len(users) != 2:
            return err("A secure private conversation must contain exactly two users.", status.HTTP_400_BAD_REQUEST)
        if ctype == Conversation.Type.GROUP and not (request.data.get("title") or "").strip():
            return err("A secure group title is required.", status.HTTP_400_BAD_REQUEST)
        if ctype == Conversation.Type.GROUP and not space_id:
            return err("A secure group must be linked to a Matrix Space.", status.HTTP_400_BAD_REQUEST)
        if ctype == Conversation.Type.PRIVATE and space_id:
            return err("A secure private chat cannot be mapped to a group Space.", status.HTTP_400_BAD_REQUEST)
        for target in users:
            if target.pk != request.user.pk and users_blocked(request.user, target):
                return err("A secure room cannot be created with a blocked user.", status.HTTP_403_FORBIDDEN)
        if Conversation.objects.filter(matrix_room_id=room_id).exists():
            return err("This Matrix room is already mapped to a Messenger conversation.", status.HTTP_409_CONFLICT)

        try:
            identities = {
                identity.user_id: identity.matrix_user_id
                for identity in MatrixIdentity.objects.filter(user__in=users)
            }
            if set(identities) != set(ids):
                return err(
                    "Matrix identities for every intended participant must be provisioned first.",
                    status.HTTP_409_CONFLICT,
                )
            verify_encrypted_room_binding(
                request.user,
                access_token,
                room_id,
                [identities[user_id] for user_id in ids],
                space_id,
            )
        except MatrixServiceError as exc:
            return _service_error_response(exc)

        title = (request.data.get("title") or "").strip()[:255]
        description = (request.data.get("description") or "").strip()[:2000]
        try:
            with transaction.atomic():
                conversation = Conversation.objects.create(
                    type=ctype,
                    title=title if ctype == Conversation.Type.GROUP else "",
                    description=description,
                    created_by=request.user,
                    security_mode=Conversation.SecurityMode.MATRIX_E2EE,
                    matrix_room_id=room_id,
                    matrix_space_id=space_id,
                    is_forum=(ctype == Conversation.Type.GROUP),
                    is_public=False,
                    is_closed=False,
                )
                for target in users:
                    ConversationParticipant.objects.create(
                        conversation=conversation,
                        user=target,
                        role=(
                            ConversationParticipant.Role.OWNER
                            if target.pk == request.user.pk
                            else ConversationParticipant.Role.MEMBER
                        ),
                        can_send_messages=True,
                        can_send_media=True,
                        can_add_members=(target.pk == request.user.pk),
                        can_pin_messages=True,
                        can_change_info=(target.pk == request.user.pk),
                    )
        except IntegrityError:
            return err("This Matrix room is already mapped or the secure-room metadata is invalid.", status.HTTP_409_CONFLICT)
        except Exception:
            logger.exception("Failed to persist Matrix room mapping for requester=%s", request.user.pk)
            return err("Could not save the secure conversation metadata.", status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            from ..message_cache import ConversationCacheService
            for target in users:
                ConversationCacheService.invalidate_user_conv_list(target.pk)
        except Exception:
            logger.exception("Failed to invalidate list cache after secure-room mapping")
        return ok(
            "Encrypted conversation registered",
            data=ConversationDetailSerializer(
                conversation,
                context=build_conversation_list_context(request, [conversation]),
            ).data,
            http_status=status.HTTP_201_CREATED,
        )
