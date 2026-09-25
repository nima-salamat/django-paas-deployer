"""Incremental usage accounting on the log database."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import LogUsageDaily, ServiceLogUsage


def _alias() -> str:
    return getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"


def bump_ingest(service_id: UUID | str, *, bytes_added: int, entries: int = 1) -> None:
    if entries <= 0 and bytes_added <= 0:
        return
    sid = str(service_id)
    now = timezone.now()
    alias = _alias()
    with transaction.atomic(using=alias):
        obj, _ = ServiceLogUsage.objects.using(alias).get_or_create(
            service_id=sid,
            defaults={
                "current_storage_bytes": 0,
                "entry_count": 0,
                "entries_dropped": 0,
                "bytes_dropped": 0,
            },
        )
        ServiceLogUsage.objects.using(alias).filter(pk=sid).update(
            current_storage_bytes=F("current_storage_bytes") + max(0, bytes_added),
            entry_count=F("entry_count") + max(0, entries),
            last_ingestion_at=now,
            updated_at=now,
        )
        day, _ = LogUsageDaily.objects.using(alias).get_or_create(
            service_id=sid, date=date.today(), defaults={}
        )
        LogUsageDaily.objects.using(alias).filter(pk=day.pk).update(
            bytes_ingested=F("bytes_ingested") + max(0, bytes_added),
            entries_ingested=F("entries_ingested") + max(0, entries),
        )


def bump_drop(service_id: UUID | str, *, entries: int, bytes_dropped: int = 0) -> None:
    if entries <= 0 and bytes_dropped <= 0:
        return
    sid = str(service_id)
    alias = _alias()
    with transaction.atomic(using=alias):
        ServiceLogUsage.objects.using(alias).get_or_create(service_id=sid, defaults={})
        ServiceLogUsage.objects.using(alias).filter(pk=sid).update(
            entries_dropped=F("entries_dropped") + max(0, entries),
            bytes_dropped=F("bytes_dropped") + max(0, bytes_dropped),
            updated_at=timezone.now(),
        )
        day, _ = LogUsageDaily.objects.using(alias).get_or_create(
            service_id=sid, date=date.today(), defaults={}
        )
        LogUsageDaily.objects.using(alias).filter(pk=day.pk).update(
            entries_dropped=F("entries_dropped") + max(0, entries),
            bytes_dropped=F("bytes_dropped") + max(0, bytes_dropped),
        )


def bump_delete(service_id: UUID | str, *, bytes_removed: int, entries: int) -> None:
    sid = str(service_id)
    alias = _alias()
    with transaction.atomic(using=alias):
        ServiceLogUsage.objects.using(alias).get_or_create(service_id=sid, defaults={})
        ServiceLogUsage.objects.using(alias).filter(pk=sid).update(
            current_storage_bytes=F("current_storage_bytes") - max(0, bytes_removed),
            entry_count=F("entry_count") - max(0, entries),
            updated_at=timezone.now(),
        )
        u = ServiceLogUsage.objects.using(alias).filter(pk=sid).first()
        if u and (u.current_storage_bytes < 0 or u.entry_count < 0):
            ServiceLogUsage.objects.using(alias).filter(pk=sid).update(
                current_storage_bytes=max(0, int(u.current_storage_bytes or 0)),
                entry_count=max(0, int(u.entry_count or 0)),
            )
        day, _ = LogUsageDaily.objects.using(alias).get_or_create(
            service_id=sid, date=date.today(), defaults={}
        )
        LogUsageDaily.objects.using(alias).filter(pk=day.pk).update(
            bytes_deleted=F("bytes_deleted") + max(0, bytes_removed),
            entries_deleted=F("entries_deleted") + max(0, entries),
        )


def get_usage(service_id: UUID | str) -> dict:
    alias = _alias()
    u = ServiceLogUsage.objects.using(alias).filter(pk=str(service_id)).first()
    if not u:
        return {
            "current_storage_bytes": 0,
            "entry_count": 0,
            "entries_dropped": 0,
            "bytes_dropped": 0,
            "last_ingestion_at": None,
        }
    return {
        "current_storage_bytes": int(u.current_storage_bytes or 0),
        "entry_count": int(u.entry_count or 0),
        "entries_dropped": int(u.entries_dropped or 0),
        "bytes_dropped": int(u.bytes_dropped or 0),
        "last_ingestion_at": u.last_ingestion_at.isoformat() if u.last_ingestion_at else None,
    }
