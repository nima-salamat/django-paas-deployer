"""Durable deployment event outbox dispatcher."""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


def dispatch_pending(*, batch_size: int = 100) -> dict[str, int]:
    from deploy.models import DeploymentEventOutbox, DeployLog

    dispatched = failed = 0
    limit = max(1, min(int(batch_size), 500))
    ids = list(
        DeploymentEventOutbox.objects
        .filter(dispatched_at__isnull=True)
        .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=timezone.now()))
        .order_by("occurred_at", "id")
        .values_list("pk", flat=True)[:limit]
    )
    for row_id in ids:
        try:
            with transaction.atomic():
                row = (
                    DeploymentEventOutbox.objects
                    .select_for_update()
                    .select_related("deployment")
                    .filter(pk=row_id, dispatched_at__isnull=True)
                    .first()
                )
                if row is None:
                    continue
                payload = dict(row.payload or {})
                event_id = row.event_id
                log_db = _log_db_alias()
                if not DeployLog.objects.using(log_db).filter(event_id=event_id).exists():
                    DeployLog.objects.using(log_db).create(
                        event_id=event_id,
                        deploy_id=row.deployment_id,
                        service_id=row.service_id,
                        stage=row.stage,
                        event_type=row.event_type,
                        level=row.level,
                        message=str(payload.get("message") or "")[:4000],
                        progress=payload.get("progress"),
                        details=payload.get("details") or payload,
                        exception_type=str(payload.get("exception_type") or ""),
                        traceback=str(payload.get("traceback") or ""),
                    )
                if not _publish(row.deployment_id, payload):
                    raise RuntimeError("Deployment event channel layer is unavailable.")
                row.dispatched_at = timezone.now()
                row.next_attempt_at = None
                row.attempts = int(row.attempts or 0) + 1
                row.last_error = ""
                row.save(update_fields=["dispatched_at", "next_attempt_at", "attempts", "last_error", "updated_at"])
                dispatched += 1
        except Exception as exc:
            failed += 1
            current = DeploymentEventOutbox.objects.filter(pk=row_id).values("attempts").first() or {}
            attempts = int(current.get("attempts") or 0) + 1
            backoff_seconds = min(300, 2 ** min(attempts, 8))
            DeploymentEventOutbox.objects.filter(pk=row_id).update(
                attempts=attempts,
                next_attempt_at=timezone.now() + __import__("datetime").timedelta(seconds=backoff_seconds),
                last_error=str(exc)[:4000],
                updated_at=timezone.now(),
            )
            logger.exception("Deployment event outbox dispatch failed for %s", row_id)
    return {"dispatched": dispatched, "failed": failed}


def _log_db_alias() -> str:
    from django.conf import settings
    return getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"


def _publish(deployment_id, payload: dict) -> bool:
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    layer = get_channel_layer()
    if layer is None:
        return False
    async_to_sync(layer.group_send)(
        f"deploy_{deployment_id}",
        {"type": "deployment.message", "payload": payload},
    )
    return True


__all__ = ["dispatch_pending"]
