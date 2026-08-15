"""Messenger API — conversations."""
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
    build_conversation_list_context, prepare_conversation_detail,
)
from ..utils import validate_messenger_file, detect_kind, users_blocked, can_see_profile_photo
from .common import ok, err, _attach_list_side_data, get_or_create_dm, logger

User = get_user_model()

class ConversationListCreateAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Scheduled delivery is handled by Celery beat — do NOT run it on every
        # list request (that alone was adding tens/hundreds of ms per call).

        page = int(request.query_params.get("page") or 1)
        page_size = min(50, int(request.query_params.get("page_size") or 30))

        # ----- Hot path: per-user conversation list cache -----
        try:
            from ..message_cache import ConversationCacheService
            cached_list = ConversationCacheService.get_user_conv_list(request.user.id)
            if cached_list is not None:
                total = len(cached_list)
                start = (page - 1) * page_size
                end = start + page_size
                return ok(data={
                    "results": cached_list[start:end],
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "has_more": end < total,
                })
        except Exception:
            logger.exception("conversation list cache read failed")

        qs = (
            Conversation.objects.filter(
                participants__user=request.user, participants__left_at__isnull=True
            )
            .distinct()
            .select_related("created_by")
            .prefetch_related(
                Prefetch(
                    "participants",
                    queryset=ConversationParticipant.objects.filter(left_at__isnull=True).select_related("user"),
                    to_attr="_prefetched_active_participants",
                )
            )
        )
        items = list(qs[:200])
        pin_map = {}
        for c in items:
            parts = getattr(c, "_prefetched_active_participants", None)
            if parts is None:
                parts = list(c.participants.all())
            part = next((p for p in parts if p.user_id == request.user.id), None)
            pin_map[c.id] = bool(part and part.is_pinned)
        items.sort(
            key=lambda c: (
                not pin_map.get(c.id, False),
                -(c.last_message_at.timestamp() if c.last_message_at else c.created_at.timestamp()),
            )
        )

        # ---- Kill N+1: bulk last_message + unread_count (2 queries total) ----
        _attach_list_side_data(items, request.user)
        ctx = build_conversation_list_context(request, items)

        start = (page - 1) * page_size
        end = start + page_size
        total = len(items)
        ser = ConversationListSerializer(items, many=True, context=ctx)
        full_data = list(ser.data)
        try:
            from ..message_cache import ConversationCacheService
            ConversationCacheService.set_user_conv_list(request.user.id, full_data)
        except Exception:
            logger.exception("conversation list cache write failed")
        return ok(data={
            "results": full_data[start:end],
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_more": end < total,
        })

    def post(self, request):
        ctype = (request.data.get("type") or "private").lower()
        if ctype == "private":
            uid = request.data.get("user_id")
            if not uid:
                return err("user_id required for private chat")
            try:
                other = User.objects.get(pk=uid, is_active=True)
            except User.DoesNotExist:
                return err("User not found", status.HTTP_404_NOT_FOUND)
            if users_blocked(request.user, other):
                return err("Cannot message blocked user")
            conv = get_or_create_dm(request.user, other)
            return ok(
                "Conversation ready",
                data=ConversationDetailSerializer(prepare_conversation_detail(conv, request.user), context=build_conversation_list_context(request, [conv])).data,
                http_status=status.HTTP_201_CREATED,
            )
        title = (request.data.get("title") or "").strip()
        if len(title) < 1:
            return err("Group title required")
        member_ids = request.data.get("member_ids") or []
        if not isinstance(member_ids, list):
            member_ids = []
        conv = Conversation.objects.create(
            type=Conversation.Type.GROUP,
            title=title[:255],
            description=(request.data.get("description") or "")[:2000],
            is_public=bool(request.data.get("is_public")),
            created_by=request.user,
        )
        ConversationParticipant.objects.create(
            conversation=conv,
            user=request.user,
            role=ConversationParticipant.Role.OWNER,
            can_send_messages=True,
            can_send_media=True,
            can_add_members=True,
            can_pin_messages=True,
            can_change_info=True,
        )
        for mid in member_ids[:100]:
            try:
                u = User.objects.get(pk=mid, is_active=True)
            except User.DoesNotExist:
                continue
            if u.id == request.user.id or users_blocked(request.user, u):
                continue
            ConversationParticipant.objects.get_or_create(
                conversation=conv, user=u,
                defaults={
                    "role": ConversationParticipant.Role.MEMBER,
                    "can_pin_messages": True,
                },
            )
        GroupInviteLink.objects.create(conversation=conv, created_by=request.user)
        return ok(
            "Group created",
            data=ConversationDetailSerializer(prepare_conversation_detail(conv, request.user), context=build_conversation_list_context(request, [conv])).data,
            http_status=status.HTTP_201_CREATED,
        )


class ConversationDetailAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_participant(self, conv, user):
        return conv.participants.filter(user=user, left_at__isnull=True).first()

    def get(self, request, pk):
        conv = get_object_or_404(
            Conversation.objects.select_related("created_by").prefetch_related(
                Prefetch(
                    "participants",
                    queryset=ConversationParticipant.objects.filter(left_at__isnull=True).select_related("user"),
                    to_attr="_prefetched_active_participants",
                )
            ),
            pk=pk,
        )
        if not self.get_participant(conv, request.user):
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        _attach_list_side_data([conv], request.user)
        ctx = build_conversation_list_context(request, [conv])
        prepare_conversation_detail(conv, request.user)
        return ok(data=ConversationDetailSerializer(conv, context=ctx).data)

    def patch(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk)
        part = self.get_participant(conv, request.user)
        if not part or (part.role not in ("owner", "admin") and not part.can_change_info):
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        if "title" in request.data and conv.type == Conversation.Type.GROUP:
            conv.title = str(request.data["title"])[:255]
        if "description" in request.data:
            conv.description = str(request.data["description"])[:2000]
        if "is_public" in request.data:
            conv.is_public = bool(request.data["is_public"])
        if "is_closed" in request.data and part.role == "owner":
            conv.is_closed = bool(request.data["is_closed"])
        # Public-group approval mode — owner only (Telegram-style "requires approval to join")
        if "requires_approval" in request.data and part.role == "owner":
            conv.requires_approval = bool(request.data["requires_approval"])
        if "members_can_add" in request.data and part.role in ("owner", "admin"):
            conv.members_can_add = bool(request.data["members_can_add"])
        # Channel-like mode — only owner/admins can toggle
        if "only_admins_send" in request.data and part.role in ("owner", "admin"):
            conv.only_admins_send = bool(request.data["only_admins_send"])
        # History visibility for new members — owner only
        if "history_visibility" in request.data and part.role == "owner":
            v = str(request.data["history_visibility"]).lower()
            if v in ("all", "from_join", "none"):
                conv.history_visibility = v
        # Group avatar upload
        if "avatar" in request.FILES:
            conv.avatar = request.FILES["avatar"]
        if "clear_avatar" in request.data and request.data["clear_avatar"]:
            conv.avatar = None
        conv.save()
        # Broadcast the change so all participants reload — important for
        # history_visibility changes (clients need to refetch messages with
        # the new filter) and for channel-mode / requires_approval toggles.
        try:
            from ..consumers import broadcast_member_change
            broadcast_member_change(conv.id, {
                "type": "group.settings_changed",
                "conversation_id": conv.id,
                "changed_by": request.user.id,
            })
        except Exception:
            pass
        return ok(data=ConversationDetailSerializer(prepare_conversation_detail(conv, request.user), context=build_conversation_list_context(request, [conv])).data)



