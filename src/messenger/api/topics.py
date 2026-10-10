"""Forum-style topics for Messenger group conversations.

The root conversation remains the General topic to preserve existing message
history and existing message, cache, and websocket behavior. Additional topics
are regular group conversations linked to the root.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from auth_users.authentication import SessionJWTAuthentication as JWTAuthentication

from ..models import Conversation, ConversationParticipant
from ..serializers import (
    ConversationDetailSerializer,
    build_conversation_list_context,
    prepare_conversation_detail,
)
from .common import ok, err


def _visible_topics(conversation, user):
    return list(
        Conversation.objects.filter(
            parent_conversation=conversation,
            participants__user=user,
            participants__left_at__isnull=True,
        ).select_related("parent_conversation").order_by("created_at")
    )


class ConversationTopicsAPIView(APIView):
    """GET topics or POST a new topic under a root group."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _conversation_and_participant(self, request, pk):
        conversation = get_object_or_404(
            Conversation.objects.select_related("created_by"),
            pk=pk,
            type=Conversation.Type.GROUP,
            parent_conversation__isnull=True,
        )
        participant = ConversationParticipant.objects.filter(
            conversation=conversation,
            user=request.user,
            left_at__isnull=True,
        ).first()
        return conversation, participant

    def get(self, request, pk):
        conversation, participant = self._conversation_and_participant(request, pk)
        if participant is None:
            return err("Forbidden", status.HTTP_403_FORBIDDEN)
        topics = _visible_topics(conversation, request.user) if conversation.is_forum else []
        return ok(data={
            "conversation_id": conversation.id,
            "is_forum": conversation.is_forum,
            "topics": [
                {
                    "id": topic.id,
                    "public_id": str(topic.public_id),
                    "title": topic.title,
                    "description": topic.description,
                    "is_closed": topic.is_closed,
                    "last_message_at": topic.last_message_at.isoformat() if topic.last_message_at else None,
                    "created_at": topic.created_at.isoformat() if topic.created_at else None,
                }
                for topic in topics
            ],
        })

    def post(self, request, pk):
        title = str(request.data.get("title") or "").strip()
        if not title:
            return err("Topic title required")
        if len(title) > 100:
            return err("Topic title must be 100 characters or fewer")

        with transaction.atomic():
            conversation, participant = self._conversation_and_participant(request, pk)
            if participant is None:
                return err("Forbidden", status.HTTP_403_FORBIDDEN)
            if participant.role not in (ConversationParticipant.Role.OWNER, ConversationParticipant.Role.ADMIN) and not participant.can_change_info:
                return err("Only group admins can create topics", status.HTTP_403_FORBIDDEN)
            if conversation.is_closed:
                return err("A closed group cannot create topics")
            if Conversation.objects.filter(
                parent_conversation=conversation,
                title__iexact=title,
            ).exists():
                return err("A topic with this name already exists")

            if not conversation.is_forum:
                conversation.is_forum = True
                conversation.save(update_fields=["is_forum", "updated_at"])

            topic = Conversation.objects.create(
                type=Conversation.Type.GROUP,
                title=title,
                description=str(request.data.get("description") or "").strip()[:2000],
                created_by=request.user,
                parent_conversation=conversation,
                is_public=False,
                is_closed=False,
                members_can_add=conversation.members_can_add,
                only_admins_send=conversation.only_admins_send,
                history_visibility=conversation.history_visibility,
            )

            active_members = list(
                ConversationParticipant.objects.filter(
                    conversation=conversation,
                    left_at__isnull=True,
                ).only(
                    "user_id", "role", "can_send_messages", "can_send_media",
                    "can_add_members", "can_pin_messages", "can_change_info",
                )
            )
            ConversationParticipant.objects.bulk_create([
                ConversationParticipant(
                    conversation=topic,
                    user_id=member.user_id,
                    role=member.role,
                    can_send_messages=member.can_send_messages,
                    can_send_media=member.can_send_media,
                    can_add_members=member.can_add_members,
                    can_pin_messages=member.can_pin_messages,
                    can_change_info=member.can_change_info,
                )
                for member in active_members
            ])

        try:
            from ..message_cache import ConversationCacheService
            ConversationCacheService.invalidate_conv_lists_for_conversation(conversation.id)
        except Exception:
            pass
        try:
            from ..consumers import broadcast_member_change
            broadcast_member_change(conversation.id, {
                "type": "group.settings_changed",
                "conversation_id": conversation.id,
                "changed_by": request.user.id,
            })
        except Exception:
            pass

        topic = (
            Conversation.objects.select_related("created_by", "parent_conversation")
            .prefetch_related(Prefetch(
                "participants",
                queryset=ConversationParticipant.objects.filter(left_at__isnull=True).select_related("user"),
                to_attr="_prefetched_active_participants",
            ))
            .get(pk=topic.pk)
        )
        detail = ConversationDetailSerializer(
            prepare_conversation_detail(topic, request.user),
            context=build_conversation_list_context(request, [topic]),
        ).data
        return ok(
            "Topic created",
            data={"topic": detail, "is_forum": True},
            http_status=status.HTTP_201_CREATED,
        )
