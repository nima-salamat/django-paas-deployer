"""Messenger API — invites."""
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


def _schedule_member_cache(conv_id, extra_user_ids=None, system_msg=None):
    """Fire-and-forget membership cache sync (Celery after commit)."""
    try:
        from ..message_cache import schedule_membership_cache_sync
        mid = getattr(system_msg, "id", None) if system_msg is not None else None
        schedule_membership_cache_sync(conv_id, extra_user_ids=extra_user_ids, system_msg_id=mid)
    except Exception:
        pass


User = get_user_model()
class InviteLinkCreateAPIView(APIView):

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk, type=Conversation.Type.GROUP)
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part or part.role not in ("owner", "admin"):
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        link = GroupInviteLink.objects.create(
            conversation=conv,
            created_by=request.user,
            max_uses=request.data.get("max_uses"),
        )
        return ok(data=GroupInviteLinkSerializer(link, context={"request": request}).data, http_status=status.HTTP_201_CREATED)


class InviteLinkRevokeAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, link_id):
        link = get_object_or_404(GroupInviteLink, pk=link_id, conversation_id=pk)
        part = ConversationParticipant.objects.filter(
            conversation_id=pk, user=request.user, left_at__isnull=True
        ).first()
        if not part or part.role not in ("owner", "admin"):
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        link.is_active = False
        link.save(update_fields=["is_active"])
        return ok("Revoked")


class JoinByInviteAPIView(APIView):
    """Join a group via invite link OR (if the group requires approval) create
    a pending join request that admins can approve/reject.

    If the group has `requires_approval=True`, this endpoint creates a
    JoinRequest (PENDING) and returns 200 with a special payload
    `{joined: False, pending: True}` so the frontend can show
    "Request sent" instead of opening the chat.

    If the group does not require approval, the user is added as a member
    immediately.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, code):
        link = get_object_or_404(GroupInviteLink, code=code)
        if not link.is_valid():
            return err("Invite link is invalid or expired")
        conv = link.conversation
        if conv.is_closed:
            return err("Group is closed")
        # If user is already an active member, just return the conversation
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
        # If the group requires approval, create a pending join request
        if getattr(conv, "requires_approval", False):
            from ..models import JoinRequest
            # Delete any prior rejected request so a new pending one can be created
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
            # Notify admins about the new request
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
            link.uses += 1
            link.save(update_fields=["uses"])
            return ok(
                "Join request sent",
                data={"joined": False, "pending": True, "request_id": req.id},
            )
        # No approval required — direct join
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
        link.uses += 1
        link.save(update_fields=["uses"])
        # Post a system message about the new member
        try:
            msg = Message.objects.create(
                conversation=conv,
                sender=request.user,
                body=f"{request.user.username} joined the group",
                is_system=True,
            )
            from ..consumers import broadcast_message, broadcast_member_change
            broadcast_message(msg)
            try:
                broadcast_member_change(conv.id, {
                    "type": "member.joined",
                    "conversation_id": conv.id,
                    "user_id": request.user.id,
                })
            except Exception:
                pass
            try:
                from ..message_cache import schedule_add_message
                schedule_add_message(msg)
            except Exception:
                pass
            _schedule_member_cache(conv.id, extra_user_ids=[request.user.id], system_msg=msg)
        except Exception:
            pass
        return ok(
            "Joined",
            data={
                "joined": True,
                "conversation": ConversationDetailSerializer(conv, context={"request": request}).data,
            },
        )



