"""Durable messenger event creation and post-commit fan-out."""
from __future__ import annotations

from django.db import transaction

from .models import MessengerEvent


def record_message_created(message):
    event = MessengerEvent.objects.create(
        event_type="message.created",
        conversation_id=message.conversation_id,
        actor_id=message.sender_id,
        message_id=message.id,
        payload={
            "message_id": message.id,
            "conversation_id": message.conversation_id,
        },
    )

    def publish():
        from .consumers import broadcast_message

        broadcast_message(message)

    transaction.on_commit(publish)
    return event
