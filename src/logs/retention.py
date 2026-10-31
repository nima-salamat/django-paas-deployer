"""Bounded retention and quota cleanup with atomic usage accounting."""
from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import LogUsageDaily, ServiceLogEntry, ServiceLogUsage
from .policy import resolve_for_service_id
from .usage import get_usage

BATCH = 2000


def _alias() -> str:
    return getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"


def _delete_batch(service_id: UUID | str, *, cutoff=None, limit: int = BATCH) -> tuple[int, int]:
    """Delete a bounded batch while holding the same quota lock as ingestion."""
    alias = _alias()
    service_key = str(service_id)
    with transaction.atomic(using=alias):
        ServiceLogUsage.objects.using(alias).get_or_create(
            service_id=service_key,
            defaults={
                "current_storage_bytes": 0, "entry_count": 0,
                "entries_dropped": 0, "bytes_dropped": 0,
            },
        )
        usage = (
            ServiceLogUsage.objects.using(alias)
            .select_for_update()
            .get(pk=service_key)
        )
        qs = ServiceLogEntry.objects.using(alias).filter(service_id=service_key)
        if cutoff is not None:
            qs = qs.filter(ts__lt=cutoff)
        rows = list(
            qs.order_by("ts", "id").values("id", "byte_size")[:max(1, int(limit))]
        )
        if not rows:
            return 0, 0

        ids = [row["id"] for row in rows]
        deleted_count, _ = (
            ServiceLogEntry.objects.using(alias)
            .filter(service_id=service_key, id__in=ids)
            .delete()
        )
        deleted_entries = min(len(rows), int(deleted_count or 0))
        if deleted_entries <= 0:
            return 0, 0

        bytes_removed = sum(
            int(row.get("byte_size") or 0) for row in rows[:deleted_entries]
        )
        usage.current_storage_bytes = max(
            0, int(usage.current_storage_bytes or 0) - bytes_removed
        )
        usage.entry_count = max(0, int(usage.entry_count or 0) - deleted_entries)
        now = timezone.now()
        ServiceLogUsage.objects.using(alias).filter(pk=service_key).update(
            current_storage_bytes=usage.current_storage_bytes,
            entry_count=usage.entry_count,
            updated_at=now,
        )
        day, _ = LogUsageDaily.objects.using(alias).get_or_create(
            service_id=service_key, date=timezone.localdate(), defaults={},
        )
        LogUsageDaily.objects.using(alias).filter(pk=day.pk).update(
            bytes_deleted=F("bytes_deleted") + bytes_removed,
            entries_deleted=F("entries_deleted") + deleted_entries,
        )
        return deleted_entries, bytes_removed


def retain_service(service_id: UUID | str) -> dict:
    policy = resolve_for_service_id(service_id)
    cutoff = timezone.now() - timedelta(days=policy.retention_days)
    deleted_total = 0
    bytes_total = 0

    while True:
        deleted, removed_bytes = _delete_batch(service_id, cutoff=cutoff)
        deleted_total += deleted
        bytes_total += removed_bytes
        if deleted < BATCH:
            break

    usage = get_usage(service_id)
    while usage["current_storage_bytes"] > policy.storage_quota_bytes:
        deleted, _ = _delete_batch(service_id)
        if deleted <= 0:
            break
        usage = get_usage(service_id)
        if deleted < BATCH:
            break

    return {"deleted": deleted_total, "bytes": bytes_total}
