"""Messenger background tasks."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger("messenger")


@shared_task(name="messenger.tasks.finalize_unanswered_call")
def finalize_unanswered_call(call_public_id: str):
    """If still ringing after 30s → no_answer + system message."""
    try:
        from .models import CallSession
        from .apis import _finish_call
        session = CallSession.objects.select_related("initiator").filter(
            public_id=call_public_id
        ).first()
        if not session:
            return
        if session.status != CallSession.Status.RINGING:
            return
        _finish_call(session, CallSession.Status.NO_ANSWER, ended_by_user=session.initiator)
    except Exception:
        logger.exception("finalize_unanswered_call failed for %s", call_public_id)



@shared_task(name="messenger.tasks.deliver_scheduled_messages")
def deliver_scheduled_messages():
    """Publish due scheduled messages (run every ~30s via celery beat)."""
    from django.utils import timezone
    from .models import Message
    now = timezone.now()
    due = list(
        Message.objects.filter(is_scheduled=True, is_deleted=False, scheduled_for__lte=now)
        .select_related("sender", "conversation")[:100]
    )
    for msg in due:
        try:
            msg.is_scheduled = False
            # Refresh created_at to "now" so it appears at the bottom of the chat
            Message.objects.filter(pk=msg.pk).update(
                is_scheduled=False,
                created_at=now,
                updated_at=now,
            )
            msg.refresh_from_db()
            from .models import Conversation
            Conversation.objects.filter(pk=msg.conversation_id).update(
                last_message_at=now, updated_at=now
            )
            from .consumers import broadcast_message
            broadcast_message(msg)
        except Exception:
            logger.exception("deliver scheduled message %s failed", msg.pk)
    return len(due)
