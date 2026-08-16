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
        from .api.calls import _finish_call
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



def deliver_due_scheduled_messages(limit=100):
    """Publish due scheduled messages. Safe to call from views (no broker required).

    Returns number of messages delivered.
    """
    from django.utils import timezone
    from .models import Message, Conversation

    now = timezone.now()
    due = list(
        Message.objects.filter(is_scheduled=True, is_deleted=False, scheduled_for__lte=now)
        .select_related("sender", "conversation", "reply_to", "reply_to__sender")
        .prefetch_related("attachments")[:limit]
    )
    delivered = 0
    for msg in due:
        try:
            # Flip flag + bump timestamps so it lands at the bottom of the chat
            Message.objects.filter(pk=msg.pk, is_scheduled=True).update(
                is_scheduled=False,
                created_at=now,
                updated_at=now,
            )
            msg.refresh_from_db()
            if msg.is_scheduled:
                # Lost a race with another worker — skip
                continue
            Conversation.objects.filter(pk=msg.conversation_id).update(
                last_message_at=now, updated_at=now
            )
            try:
                from .message_cache import schedule_add_message
                schedule_add_message(msg)
            except Exception:
                logger.exception("cache delivered scheduled message %s failed", msg.pk)
            try:
                from .consumers import broadcast_message
                broadcast_message(msg)
            except Exception:
                logger.exception("broadcast delivered scheduled message %s failed", msg.pk)
            delivered += 1
        except Exception:
            logger.exception("deliver scheduled message %s failed", msg.pk)
    return delivered


@shared_task(name="messenger.tasks.deliver_scheduled_messages")
def deliver_scheduled_messages():
    """Celery entrypoint — also used by admin force-deliver."""
    return deliver_due_scheduled_messages()


@shared_task(name="messenger.tasks.purge_view_once_if_complete", ignore_result=True)
def purge_view_once_if_complete(attachment_id: int):
    """After view windows elapse, delete file if all recipients already opened."""
    try:
        from .models import MessageAttachment
        from .api.media import maybe_purge_view_once_attachment
        att = MessageAttachment.objects.filter(pk=attachment_id).first()
        if att:
            return maybe_purge_view_once_attachment(att)
    except Exception:
        logger.exception("purge_view_once_if_complete failed id=%s", attachment_id)
    return False
