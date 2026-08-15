"""Shared helpers for messenger API modules."""
from __future__ import annotations

import logging
from django.db.models import Count, Prefetch, Q
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.response import Response

from ..models import (
    Conversation, ConversationParticipant, Message, MessageAttachment,
)

User = get_user_model()
logger = logging.getLogger("messenger")

def ok(message="success", data=None, http_status=status.HTTP_200_OK):
    body = {"success": True, "message": message}
    if data is not None:
        body["data"] = data
    return Response(body, status=http_status)


def err(message, http_status=status.HTTP_400_BAD_REQUEST, extra=None):
    body = {"success": False, "message": message}
    if extra:
        body.update(extra)
    return Response(body, status=http_status)


def _attach_list_side_data(conversations, user):
    """Attach last_message + unread_count on each Conversation in O(1) queries.

    Without this, ConversationListSerializer issues 2+ queries *per chat*
    (last message + unread count) — the main reason the list felt "broken slow".
    """
    if not conversations:
        return
    conv_ids = [c.id for c in conversations]

    # --- last non-deleted, non-scheduled message per conversation (1 query) ---
    # DISTINCT ON is Postgres-specific; project already uses postgres.
    last_rows = (
        Message.objects.filter(
            conversation_id__in=conv_ids,
            is_deleted=False,
            is_scheduled=False,
        )
        .order_by("conversation_id", "-created_at", "-id")
        .distinct("conversation_id")
        .only(
            "id", "conversation_id", "body", "sender_id", "created_at",
            "is_system", "is_scheduled",
        )
    )
    last_by_conv = {m.conversation_id: m for m in last_rows}

    # attachments existence for those last messages (1 query)
    last_ids = [m.id for m in last_by_conv.values()]
    att_ids = set()
    if last_ids:
        att_ids = set(
            MessageAttachment.objects.filter(message_id__in=last_ids)
            .values_list("message_id", flat=True)
            .distinct()
        )

    # --- unread counts: one grouped SQL join (not N COUNT queries) ---
    from django.db import connection
    unread_map = {cid: 0 for cid in conv_ids}
    if conv_ids:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT m.conversation_id, COUNT(*)
                FROM messenger_message m
                INNER JOIN messenger_conversationparticipant p
                    ON p.conversation_id = m.conversation_id
                   AND p.user_id = %s
                   AND p.left_at IS NULL
                WHERE m.conversation_id = ANY(%s)
                  AND m.is_deleted = FALSE
                  AND m.is_scheduled = FALSE
                  AND (m.sender_id IS NULL OR m.sender_id <> %s)
                  AND (p.last_read_at IS NULL OR m.created_at > p.last_read_at)
                GROUP BY m.conversation_id
                """,
                [user.id, conv_ids, user.id],
            )
            for cid, cnt in cursor.fetchall():
                unread_map[int(cid)] = int(cnt)

    for c in conversations:
        msg = last_by_conv.get(c.id)
        if msg is not None:
            msg._has_attachments = msg.id in att_ids
        c._prefetched_last_message = msg
        c.annotated_unread = unread_map.get(c.id, 0)



def get_or_create_dm(user_a, user_b) -> Conversation:
    if user_a.id > user_b.id:
        user_a, user_b = user_b, user_a
    existing = (
        Conversation.objects.filter(type=Conversation.Type.PRIVATE)
        .annotate(pc=Count("participants"))
        .filter(pc=2)
        .filter(participants__user=user_a)
        .filter(participants__user=user_b)
        .distinct()
        .first()
    )
    if existing:
        return existing
    conv = Conversation.objects.create(type=Conversation.Type.PRIVATE, created_by=user_a)
    ConversationParticipant.objects.create(conversation=conv, user=user_a, role=ConversationParticipant.Role.OWNER)
    ConversationParticipant.objects.create(conversation=conv, user=user_b, role=ConversationParticipant.Role.MEMBER)
    return conv


