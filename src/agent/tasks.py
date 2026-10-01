"""Agent control-plane maintenance tasks."""
from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from .models import AgentEnrollmentToken, AgentIdempotencyRecord

logger = logging.getLogger("agent.tasks")


@shared_task(
    bind=True,
    max_retries=0,
    name="agent.tasks.cleanup_expired_state",
)
def cleanup_expired_state(self) -> dict[str, int]:
    """Bound the retention of short-lived bootstrap and idempotency state."""
    now = timezone.now()
    enrollment_deleted, _ = AgentEnrollmentToken.objects.filter(
        expires_at__lte=now
    ).delete()
    idempotency_deleted, _ = AgentIdempotencyRecord.objects.filter(
        expires_at__lte=now
    ).delete()
    logger.info(
        "Agent maintenance cleaned enrollment=%s idempotency=%s",
        enrollment_deleted,
        idempotency_deleted,
    )
    return {
        "enrollment_deleted": enrollment_deleted,
        "idempotency_deleted": idempotency_deleted,
    }
