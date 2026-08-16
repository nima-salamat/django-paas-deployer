"""Messenger API — groups."""
from __future__ import annotations

import os
import uuid
import secrets
import logging
import mimetypes
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q, Count, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from ..models import (
    Contact, Block, Conversation, ConversationParticipant, Message,
    MessageReaction, MessageAttachment, GroupInviteLink,
    ProfilePhotoPrivacy, ProfilePhotoAllowed, MessageReadReceipt, UserBio,
    JoinRequest, PinnedMessage, CallSession,
)
from ..serializers import (
    UserMiniSerializer, MessageSerializer, ConversationListSerializer,
    ConversationDetailSerializer, ContactSerializer,
    GroupInviteLinkSerializer, ProfilePhotoSerializer, ProfilePhotoPrivacySerializer,
    build_message_list_context, build_user_mini_context,
)
from ..utils import validate_messenger_file, detect_kind, users_blocked, can_see_profile_photo
from .common import ok, err, _attach_list_side_data, get_or_create_dm, logger


def _schedule_member_cache(conv_id, extra_user_ids=None, system_msg=None):
    """Fire-and-forget membership cache sync (Celery after commit)."""
    try:
        from ..message_cache import schedule_membership_cache_sync
        mid = getattr(system_msg, "id", None) if system_msg is not None else None
        schedule_membership_cache_sync(conv_id, extra_user_ids=extra_user_ids, system_msg_id=mid)
    except Exception:
        pass


User = get_user_model()
class PublicGroupSearchAPIView(APIView):
    """Search public groups.

    Returns an EMPTY list when the query is empty — public groups are NEVER
    listed automatically. Users must actively search by name/description to
    discover them (Telegram-like behaviour for public groups/channels).

    Includes `my_pending_request` flag for each group so the frontend can
    show a "Request sent" / "Cancel request" button on groups that require
    approval.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 1:
            return ok(data=[])
        qs = (
            Conversation.objects.filter(
                type=Conversation.Type.GROUP, is_public=True, is_closed=False,
            )
            .filter(Q(title__icontains=q) | Q(description__icontains=q))
            .order_by("-last_message_at")[:50]
        )
        items = list(qs)
        # Annotate each group with the viewer's pending join request (if any)
        # and whether they're already a member.
        my_pending_map = {}
        my_member_map = {}
        if items:
            from ..models import JoinRequest
            pending = JoinRequest.objects.filter(
                user=request.user,
                conversation__in=items,
                status=JoinRequest.Status.PENDING,
            ).values_list("conversation_id", flat=True)
            my_pending_map = set(pending)
            my_member_map = set(
                ConversationParticipant.objects.filter(
                    user=request.user,
                    conversation__in=items,
                    left_at__isnull=True,
                ).values_list("conversation_id", flat=True)
            )
        out = []
        for c in items:
            d = ConversationListSerializer(c, context={"request": request}).data
            d["my_pending_request"] = c.id in my_pending_map
            d["is_member"] = c.id in my_member_map
            out.append(d)
        return ok(data=out)



class GroupAvatarAPIView(APIView):
    """Upload or clear a group's avatar (owner/admin only).

    POST   /conversations/<pk>/avatar/   (multipart: avatar=<file>)   -> upload
    DELETE /conversations/<pk>/avatar/                                -> clear
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk, type=Conversation.Type.GROUP)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part or part.role not in ("owner", "admin"):
            return err("Only admins can change the group avatar", status.HTTP_403_FORBIDDEN)
        f = request.FILES.get("avatar")
        if not f:
            return err("avatar file required")
        # Basic size check (10MB)
        if getattr(f, "size", 0) > 10 * 1024 * 1024:
            return err("Image too large (max 10MB)")
        # Validate it is actually an image (Django ImageField requires Pillow;
        # we use a FileField, so do a manual content-type sanity check).
        ctype = (getattr(f, "content_type", "") or "").lower()
        if ctype and not ctype.startswith("image/"):
            return err("File must be an image")
        # Delete the previous avatar file from storage (if any) BEFORE
        # assigning the new one — otherwise the old file lingers and may
        # conflict with the new name on case-insensitive filesystems.
        old_avatar = conv.avatar
        if old_avatar:
            try:
                old_avatar.delete(save=False)
            except Exception:
                logger.warning("Could not delete previous group avatar", exc_info=True)
        # Assign new file. Django's FileField.save() will write the file
        # to MEDIA_ROOT/messenger/groups/<unique-name> using the storage backend.
        # We use a deterministic, unique filename to avoid collisions and
        # make the URL predictable for the client.
        import os
        import uuid
        ext = os.path.splitext(f.name)[1].lower() or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
            ext = ".jpg"
        safe_name = f"group_{conv.pk}_{uuid.uuid4().hex[:12]}{ext}"
        f.name = safe_name
        try:
            conv.avatar = f
            conv.save(update_fields=["avatar", "updated_at"])
        except Exception as save_exc:
            logger.error("Group avatar save failed: %s", save_exc, exc_info=True)
            return err(
                f"Could not save image: {save_exc}",
                status.HTTP_400_BAD_REQUEST,
            )
        # Force a refresh from DB so the serializer returns the committed path
        conv.refresh_from_db()
        # Verify the file actually exists on disk (debug aid — surfaces
        # misconfigured MEDIA_ROOT / volume mounts early).
        try:
            from django.conf import settings
            path = conv.avatar.path if hasattr(conv.avatar, "path") else None
            if path and not os.path.exists(path):
                logger.error(
                    "Group avatar file missing after save: %s (MEDIA_ROOT=%s)",
                    path, getattr(settings, "MEDIA_ROOT", "<unset>"),
                )
        except Exception:
            pass
        return ok("Avatar updated", data=ConversationDetailSerializer(conv, context={"request": request}).data)

    def delete(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk, type=Conversation.Type.GROUP)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part or part.role not in ("owner", "admin"):
            return err("Only admins can change the group avatar", status.HTTP_403_FORBIDDEN)
        if conv.avatar:
            # Delete the file from storage
            try:
                conv.avatar.delete(save=False)
            except Exception:
                pass
            conv.avatar = None
            conv.save(update_fields=["avatar", "updated_at"])
        return ok("Avatar removed", data=ConversationDetailSerializer(conv, context={"request": request}).data)


# ---------------------------------------------------------------------------
# Join Requests (Telegram-style — for public groups that require approval)
# ---------------------------------------------------------------------------

class PublicGroupJoinAPIView(APIView):
    """Join a public group directly (no invite code required).

    If the group has `requires_approval=True`, this creates a pending
    JoinRequest and returns `{joined: False, pending: True}`.

    If the group does NOT require approval, the user is added as a member
    immediately and the conversation payload is returned.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        conv = get_object_or_404(
            Conversation, pk=pk,
            type=Conversation.Type.GROUP, is_public=True, is_closed=False,
        )
        # Already an active member?
        existing = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if existing:
            return ok(
                "Already a member",
                data={
                    "joined": True,
                    "conversation": ConversationDetailSerializer(conv, context={"request": request}).data,
                },
            )
        # Approval required -> create a pending request
        if getattr(conv, "requires_approval", False):
            from ..models import JoinRequest
            # Clear any prior rejected request so a fresh pending one can be created
            JoinRequest.objects.filter(
                user=request.user, conversation=conv, status=JoinRequest.Status.REJECTED
            ).delete()
            req, created = JoinRequest.objects.get_or_create(
                user=request.user, conversation=conv,
                defaults={"status": JoinRequest.Status.PENDING},
            )
            if not created and req.status == JoinRequest.Status.PENDING:
                return ok(
                    "Request already pending",
                    data={"joined": False, "pending": True, "request_id": req.id},
                )
            try:
                from ..consumers import broadcast_join_request
                broadcast_join_request(conv.id, {
                    "type": "join_request.new",
                    "conversation_id": conv.id,
                    "request_id": req.id,
                    "user_id": request.user.id,
                })
            except Exception:
                pass
            return ok(
                "Join request sent",
                data={"joined": False, "pending": True, "request_id": req.id},
            )
        # Direct join
        part, created = ConversationParticipant.objects.get_or_create(
            conversation=conv,
            user=request.user,
            defaults={
                "role": ConversationParticipant.Role.MEMBER,
                "can_pin_messages": True,
            },
        )
        if not created and part.left_at:
            from django.utils import timezone as _tz
            part.left_at = None
            part.joined_at = _tz.now()
            part.save(update_fields=["left_at", "joined_at"])
        # System message about the new member
        try:
            msg = Message.objects.create(
                conversation=conv,
                sender=request.user,
                body=f"{request.user.username} joined the group",
                is_system=True,
            )
            from ..consumers import broadcast_message, broadcast_member_change
            broadcast_message(msg)
            broadcast_member_change(conv.id, {
                "type": "member.joined",
                "conversation_id": conv.id,
                "user_id": request.user.id,
            })
            try:
                from ..message_cache import schedule_add_message
                schedule_add_message(msg)
            except Exception:
                pass
            _schedule_member_cache(conv.id, extra_user_ids=[request.user.id], system_msg=msg)
        except Exception:
            _schedule_member_cache(conv.id, extra_user_ids=[request.user.id])
        return ok(
            "Joined",
            data={
                "joined": True,
                "conversation": ConversationDetailSerializer(conv, context={"request": request}).data,
            },
        )


class JoinRequestListAPIView(APIView):
    """List pending join requests for a group (admins only).

    GET /conversations/<pk>/join-requests/   -> [{ id, user, status, created_at }, ...]
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk, type=Conversation.Type.GROUP)
        my_part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not my_part or my_part.role not in ("owner", "admin"):
            return err("Only admins can view join requests", status.HTTP_403_FORBIDDEN)
        qs = (
            conv.join_requests.filter(status=JoinRequest.Status.PENDING)
            .select_related("user", "decided_by")
            .order_by("-created_at")
        )
        from ..serializers import JoinRequestSerializer
        return ok(data=JoinRequestSerializer(qs, many=True, context={"request": request}).data)


class JoinRequestActionAPIView(APIView):
    """Approve or reject a pending join request (admins only).

    POST /conversations/<pk>/join-requests/<req_id>/action/
      body: { "action": "approve" | "reject" }

    On approve: the requesting user is added as a member + the request is
    marked APPROVED + a system message is posted + the user is notified
    via their personal WS channel so their client opens the chat.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, req_id):
        conv = get_object_or_404(Conversation, pk=pk, type=Conversation.Type.GROUP)
        my_part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not my_part or my_part.role not in ("owner", "admin"):
            return err("Only admins can act on join requests", status.HTTP_403_FORBIDDEN)
        try:
            req = conv.join_requests.get(pk=req_id)
        except JoinRequest.DoesNotExist:
            return err("Join request not found", status.HTTP_404_NOT_FOUND)
        if req.status != JoinRequest.Status.PENDING:
            return err(f"Request already {req.status}")
        action = (request.data.get("action") or "").strip().lower()
        if action not in ("approve", "reject"):
            return err("action must be 'approve' or 'reject'")
        req.decided_by = request.user
        req.decided_at = timezone.now()
        if action == "approve":
            req.status = JoinRequest.Status.APPROVED
            # Add the user as a member
            part, created = ConversationParticipant.objects.get_or_create(
                conversation=conv,
                user=req.user,
                defaults={
                    "role": ConversationParticipant.Role.MEMBER,
                    "can_pin_messages": True,
                },
            )
            if not created and part.left_at:
                from django.utils import timezone as _tz
                part.left_at = None
                part.joined_at = _tz.now()
                part.save(update_fields=["left_at", "joined_at"])
            # System message
            try:
                msg = Message.objects.create(
                    conversation=conv,
                    sender=request.user,
                    body=f"{req.user.username} joined the group",
                    is_system=True,
                )
                from ..consumers import broadcast_message, broadcast_member_change, broadcast_join_request
                broadcast_message(msg)
                broadcast_member_change(conv.id, {
                    "type": "member.joined",
                    "conversation_id": conv.id,
                    "user_id": req.user_id,
                })
                # Notify the requester that they were approved
                broadcast_join_request(conv.id, {
                    "type": "join_request.approved",
                    "conversation_id": conv.id,
                    "request_id": req.id,
                    "user_id": req.user_id,
                })
                try:
                    from ..message_cache import schedule_add_message
                    schedule_add_message(msg)
                except Exception:
                    pass
                _schedule_member_cache(conv.id, extra_user_ids=[req.user_id], system_msg=msg)
            except Exception:
                _schedule_member_cache(conv.id, extra_user_ids=[req.user_id])
        else:
            req.status = JoinRequest.Status.REJECTED
            try:
                from ..consumers import broadcast_join_request
                broadcast_join_request(conv.id, {
                    "type": "join_request.rejected",
                    "conversation_id": conv.id,
                    "request_id": req.id,
                    "user_id": req.user_id,
                })
            except Exception:
                pass
        # The user asked that requests be DELETED after the admin acts on them
        # (the operation is complete — there's no reason to keep a decided
        # request around cluttering the admin's list or the user's "My
        # requests" list). We broadcast the decision BEFORE deleting so the
        # frontend can show the "approved/rejected" toast.
        req.save(update_fields=["status", "decided_by", "decided_at"])
        req_id = req.id
        req_status = req.status
        req_user_id = req.user_id
        req.delete()
        return ok(f"Request {req_status}", data={"status": req_status, "request_id": req_id, "user_id": req_user_id})


class MyJoinRequestsAPIView(APIView):
    """List all of the current user's join requests (any status).

    GET /me/join-requests/  -> [{ id, conversation, conversation_title, status, created_at, ... }]
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            JoinRequest.objects.filter(user=request.user)
            .select_related("conversation", "decided_by")
            .order_by("-created_at")
        )
        from ..serializers import JoinRequestSerializer
        return ok(data=JoinRequestSerializer(qs, many=True, context={"request": request}).data)


class JoinRequestCancelAPIView(APIView):
    """Cancel (delete) the current user's own pending join request.

    DELETE /join-requests/<req_id>/  -> 200 OK

    The user can only cancel their OWN pending requests. Once approved or
    rejected, the request can no longer be cancelled (the user can leave
    the group separately if approved).
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, req_id):
        try:
            req = JoinRequest.objects.get(pk=req_id, user=request.user)
        except JoinRequest.DoesNotExist:
            return err("Join request not found", status.HTTP_404_NOT_FOUND)
        if req.status != JoinRequest.Status.PENDING:
            return err(f"Cannot cancel a {req.status} request")
        conv_id = req.conversation_id
        req.delete()
        # Notify admins that the request was cancelled (so their UI updates)
        try:
            from ..consumers import broadcast_join_request
            broadcast_join_request(conv_id, {
                "type": "join_request.cancelled",
                "conversation_id": conv_id,
                "user_id": request.user.id,
            })
        except Exception:
            pass
        return ok("Request cancelled")



