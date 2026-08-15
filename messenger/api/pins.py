"""Messenger API — pins."""
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
class ConversationPinAPIView(APIView):
    """Toggle pin/unpin of a conversation for the current user (per-user pin)."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        part = ConversationParticipant.objects.filter(
            conversation_id=pk, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        part.is_pinned = not part.is_pinned
        part.pinned_at = timezone.now() if part.is_pinned else None
        part.save(update_fields=["is_pinned", "pinned_at"])
        return ok(
            "Pinned" if part.is_pinned else "Unpinned",
            data={"is_pinned": part.is_pinned},
        )


class MessagePinAPIView(APIView):
    """Pin or unpin a specific message in its conversation.

    POST /messages/<pk>/pin/  — toggle pin on/off.

    Only participants with `can_pin_messages` (or owner/admin) may pin.
    Returns the current pin state and the list of pinned message ids for
    the conversation so the frontend can update its bar in one round-trip.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        msg = get_object_or_404(Message, pk=pk, is_deleted=False)
        conv = msg.conversation
        part = ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).first()
        if not part:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        # Permission check: owner/admin always allowed.
        # In private (direct) chats, every participant can pin.
        # In group chats, non-owner/admin needs explicit can_pin_messages.
        if conv.type != Conversation.Type.PRIVATE:
            if part.role not in ("owner", "admin") and not part.can_pin_messages:
                return err("You don't have permission to pin messages", status.HTTP_403_FORBIDDEN)

        existing = PinnedMessage.objects.filter(conversation=conv, message=msg).first()
        if existing:
            existing.delete()
            pinned = False
        else:
            PinnedMessage.objects.create(conversation=conv, message=msg, pinned_by=request.user)
            pinned = True

        # Return all pinned message ids for this conversation (newest-first)
        pin_ids = list(
            PinnedMessage.objects.filter(conversation=conv)
            .select_related("message")
            .order_by("-pinned_at")
            .values_list("message_id", flat=True)
        )

        # Broadcast to other participants so their pinned bar updates
        try:
            from ..consumers import broadcast_pin
            broadcast_pin(conv.id, {
                "type": "message.pinned" if pinned else "message.unpinned",
                "conversation_id": conv.id,
                "message_id": msg.id,
                "pinned_by": request.user.id,
                "pinned_message_ids": pin_ids,
            })
        except Exception:
            pass

        return ok(
            "Pinned" if pinned else "Unpinned",
            data={"pinned": pinned, "message_id": msg.id, "pinned_message_ids": pin_ids},
        )


class ConversationPinnedMessagesAPIView(APIView):
    """List all pinned messages for a conversation (newest-pinned-first).

    GET /conversations/<pk>/pinned-messages/

    Returns a list of { id, message, pinned_at } objects.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk)
        if not ConversationParticipant.objects.filter(
            conversation=conv, user=request.user, left_at__isnull=True
        ).exists():
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        pins = (
            PinnedMessage.objects.filter(conversation=conv, message__is_deleted=False)
            .select_related("message", "message__sender", "pinned_by")
            .order_by("-pinned_at")
        )
        data = [
            {
                "id": p.id,
                "message": MessageSerializer(p.message, context={"request": request}).data,
                "pinned_by": UserMiniSerializer(p.pinned_by, context={"request": request}).data if p.pinned_by else None,
                "pinned_at": p.pinned_at,
            }
            for p in pins
        ]
        return ok(data=data)


class MessageReadersAPIView(APIView):
    """Returns full read receipt breakdown for a single message:
    { read: [...], unread: [...], conversation_id, sender_id, created_at }
    Used by the "Seen by" right-click submenu.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        msg = get_object_or_404(Message, pk=pk, is_deleted=False)
        if not ConversationParticipant.objects.filter(
            conversation=msg.conversation, user=request.user, left_at__isnull=True
        ).exists():
            return err("Forbidden", status.HTTP_403_FORBIDDEN)

        participants = list(
            ConversationParticipant.objects.filter(
                conversation=msg.conversation, left_at__isnull=True
            ).select_related("user")
        )
        # Build read set from MessageReadReceipt
        receipt_users = {}  # user_id -> seen_at
        for r in msg.read_receipts.all():
            receipt_users[r.user_id] = r.seen_at
        # Supplement with last_read_at
        read_list = []
        unread_list = []
        for p in participants:
            seen_at = receipt_users.get(p.user_id)
            if not seen_at and p.last_read_at and p.last_read_at >= msg.created_at:
                seen_at = p.last_read_at
            entry = {
                "user": UserMiniSerializer(p.user, context={"request": request}).data,
                "seen_at": seen_at,
                "role": p.role,
            }
            if seen_at:
                read_list.append(entry)
            elif p.user_id != msg.sender_id:
                # Sender always implicitly "saw" their own message
                unread_list.append(entry)
            else:
                read_list.append(entry)  # sender counts as read
        return ok(data={
            "message_id": msg.id,
            "conversation_id": msg.conversation_id,
            "sender_id": msg.sender_id,
            "created_at": msg.created_at,
            "read": read_list,
            "unread": unread_list,
        })



