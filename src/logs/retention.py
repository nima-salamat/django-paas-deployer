"""Celery-oriented retention and quota cleanup (maintenance only)."""
from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.utils import timezone

from .models import ServiceLogEntry
from .policy import resolve_for_service_id
from .usage import bump_delete, get_usage

logger = logging.getLogger(__name__)

BATCH = 2000


def _alias() -> str:
    return getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"


def retain_service(service_id: UUID | str) -> dict:
    policy = resolve_for_service_id(service_id)
    alias = _alias()
    cutoff = timezone.now() - timedelta(days=policy.retention_days)
    deleted_total = 0
    bytes_total = 0
    while True:
        batch = list(
            ServiceLogEntry.objects.using(alias)
            .filter(service_id=str(service_id), ts__lt=cutoff)
            .order_by("ts")[:BATCH]
        )
        if not batch:
            break
        ids = [e.id for e in batch]
        b = sum(int(e.byte_size or 0) for e in batch)
        ServiceLogEntry.objects.using(alias).filter(id__in=ids).delete()
        deleted_total += len(ids)
        bytes_total += b
        if len(batch) < BATCH:
            break
    if deleted_total:
        bump_delete(service_id, bytes_removed=bytes_total, entries=deleted_total)

    # Secondary FIFO if over quota
    usage = get_usage(service_id)
    while usage["current_storage_bytes"] > policy.storage_quota_bytes:
        batch = list(
            ServiceLogEntry.objects.using(alias)
            .filter(service_id=str(service_id))
            .order_by("ts", "seq")[:BATCH]
        )
        if not batch:
            break
        ids = [e.id for e in batch]
        b = sum(int(e.byte_size or 0) for e in batch)
        ServiceLogEntry.objects.using(alias).filter(id__in=ids).delete()
        bump_delete(service_id, bytes_removed=b, entries=len(ids))
        usage = get_usage(service_id)
        if len(batch) < BATCH:
            break

    return {"deleted": deleted_total, "bytes": bytes_total}
