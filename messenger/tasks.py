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
