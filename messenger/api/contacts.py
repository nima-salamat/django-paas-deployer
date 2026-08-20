"""Messenger API — contacts."""
from __future__ import annotations

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

User = get_user_model()


def _invalidate_user_scoped_messenger_cache(user_id):
    """Invalidate viewer-specific conversation-list data after contact/block changes."""
    try:
        from ..message_cache import ConversationCacheService
        ConversationCacheService.invalidate_user_conv_list(int(user_id))
    except Exception:
        logger.exception("failed to invalidate messenger list cache for user=%s", user_id)
class UserSearchPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class UserSearchAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 1:
            return ok(data={"results": [], "next": None})
        blocked_ids = set(
            Block.objects.filter(blocker=request.user).values_list("blocked_id", flat=True)
        ) | set(
            Block.objects.filter(blocked=request.user).values_list("blocker_id", flat=True)
        )
        qs = (
            User.objects.filter(username__icontains=q, is_active=True)
            .exclude(id=request.user.id)
            .exclude(id__in=blocked_ids)
            .order_by("username")
        )
        paginator = UserSearchPagination()
        page = paginator.paginate_queryset(qs, request)
        ser = UserMiniSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(ser.data)


class ContactListCreateAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = list(Contact.objects.filter(owner=request.user).select_related("contact").order_by("-created_at"))
        user_ids = [c.contact_id for c in qs if c.contact_id]
        ctx = build_user_mini_context(request.user, user_ids)
        ctx["request"] = request
        return ok(data=ContactSerializer(qs, many=True, context=ctx).data)

    def post(self, request):
        uid = request.data.get("user_id")
        if not uid:
            return err("user_id required")
        try:
            target = User.objects.get(pk=uid, is_active=True)
        except User.DoesNotExist:
            return err("User not found", status.HTTP_404_NOT_FOUND)
        if target.id == request.user.id:
            return err("Cannot add yourself")
        if users_blocked(request.user, target):
            return err("User is blocked")
        obj, created = Contact.objects.get_or_create(
            owner=request.user, contact=target,
            defaults={"nickname": (request.data.get("nickname") or "").strip()[:120]},
        )
        _invalidate_user_scoped_messenger_cache(request.user.id)
        return ok(
            "Contact added" if created else "Already in contacts",
            data=ContactSerializer(obj, context={"request": request}).data,
            http_status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ContactDeleteAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, user_id):
        deleted, _ = Contact.objects.filter(owner=request.user, contact_id=user_id).delete()
        if deleted:
            _invalidate_user_scoped_messenger_cache(request.user.id)
        return ok("Removed" if deleted else "Not found")


class BlockListCreateAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ids = Block.objects.filter(blocker=request.user).values_list("blocked_id", flat=True)
        users = User.objects.filter(id__in=ids)
        return ok(data=UserMiniSerializer(users, many=True, context={"request": request}).data)

    def post(self, request):
        uid = request.data.get("user_id")
        if not uid:
            return err("user_id required")
        try:
            target = User.objects.get(pk=uid)
        except User.DoesNotExist:
            return err("User not found", status.HTTP_404_NOT_FOUND)
        if target.id == request.user.id:
            return err("Cannot block yourself")
        Block.objects.get_or_create(blocker=request.user, blocked=target)
        Contact.objects.filter(owner=request.user, contact=target).delete()
        _invalidate_user_scoped_messenger_cache(request.user.id)
        return ok("Blocked", http_status=status.HTTP_201_CREATED)


class UnblockAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        deleted, _ = Block.objects.filter(blocker=request.user, blocked_id=user_id).delete()
        if deleted:
            _invalidate_user_scoped_messenger_cache(request.user.id)
        return ok("Unblocked")



