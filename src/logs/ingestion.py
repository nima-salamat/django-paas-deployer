"""Idempotent runtime log ingestion with checkpoints, quota, rate awareness."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Iterable
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import LogUsageDaily, ServiceLogEntry, ServiceLogStream, ServiceLogUsage
from .policy import EffectiveLoggingPolicy, resolve_for_service_id
from .usage import get_usage

logger = logging.getLogger(__name__)


def _alias() -> str:
    return getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"


def fingerprint(ts: datetime, stream: str, message: str) -> str:
    raw = f"{ts.isoformat()}|{stream}|{message}".encode("utf-8", "replace")
    return hashlib.sha256(raw).hexdigest()


def infer_level(message: str) -> str:
    m = (message or "").lower()
    if "critical" in m or "fatal" in m:
        return "critical"
    if "error" in m or "exception" in m:
        return "error"
    if "warn" in m:
        return "warning"
    if "debug" in m:
        return "debug"
    if "info" in m:
        return "info"
    return ""


def _redact(text: str) -> str:
    """Redact before persistence; never fall back to storing raw input."""
    from deployments.common.security import redact_secrets

    redacted = redact_secrets(text or "")
    if not isinstance(redacted, str):
        raise RuntimeError("Log redaction returned a non-text value")
    return redacted


def lease_is_current(stream: ServiceLogStream, owner_id: str, *, now=None) -> bool:
    """Return True only while this exact collector still owns a live lease."""
    now = now or timezone.now()
    return (
        str(getattr(stream, "owner_id", "") or "") == str(owner_id)
        and getattr(stream, "lease_until", None) is not None
        and stream.lease_until > now
    )


def acquire_lease(stream: ServiceLogStream, owner_id: str, *, lease_seconds: int = 30) -> bool:
    alias = _alias()
    now = timezone.now()
    with transaction.atomic(using=alias):
        locked = (
            ServiceLogStream.objects.using(alias)
            .select_for_update()
            .filter(pk=stream.pk)
            .first()
        )
        if locked is None:
            return False
        if locked.owner_id and locked.lease_until and locked.lease_until > now:
            if locked.owner_id != owner_id:
                return False
        locked.owner_id = owner_id
        locked.lease_until = now + timedelta(seconds=lease_seconds)
        locked.lease_token = owner_id
        locked.heartbeat_at = now
        locked.save(update_fields=["owner_id", "lease_until", "lease_token", "heartbeat_at", "updated_at"])
        stream.owner_id = locked.owner_id
        stream.lease_until = locked.lease_until
        stream.lease_token = locked.lease_token
        return True


def heartbeat_lease(stream: ServiceLogStream, owner_id: str, *, lease_seconds: int = 30) -> bool:
    alias = _alias()
    now = timezone.now()
    updated = (
        ServiceLogStream.objects.using(alias)
        .filter(pk=stream.pk, owner_id=owner_id)
        .update(
            lease_until=now + timedelta(seconds=lease_seconds),
            heartbeat_at=now,
            updated_at=now,
        )
    )
    return updated > 0


def get_or_create_stream(
    *,
    service_id: UUID | str,
    container_id: str,
    container_name: str = "",
    deploy_id: UUID | str | None = None,
) -> ServiceLogStream:
    alias = _alias()
    filters = {
        "service_id": str(service_id),
        "container_id": container_id,
        "status": ServiceLogStream.Status.ACTIVE,
    }
    existing = ServiceLogStream.objects.using(alias).filter(**filters).first()
    if existing:
        return existing

    # Reuse the most recent closed/lost stream for the same immutable runtime
    # resource. Swarm reconnects and collector restarts must continue from the
    # existing checkpoint; creating a fresh stream would replay the catch-up
    # window and defeat stream-level fingerprint deduplication.
    try:
        with transaction.atomic(using=alias):
            existing = (
                ServiceLogStream.objects.using(alias)
                .select_for_update()
                .filter(
                    service_id=str(service_id),
                    container_id=container_id,
                )
                .exclude(status=ServiceLogStream.Status.ACTIVE)
                .order_by("-started_at", "-id")
                .first()
            )
            if existing:
                existing.status = ServiceLogStream.Status.ACTIVE
                existing.ended_at = None
                existing.owner_id = ""
                existing.lease_until = None
                existing.lease_token = ""
                existing.heartbeat_at = None
                existing.container_name = container_name or existing.container_name
                existing.deploy_id = str(deploy_id) if deploy_id else existing.deploy_id
                existing.save(update_fields=[
                    "status", "ended_at", "owner_id", "lease_until",
                    "lease_token", "heartbeat_at", "container_name",
                    "deploy_id", "updated_at",
                ])
                return existing

            return ServiceLogStream.objects.using(alias).create(
                service_id=str(service_id),
                deploy_id=str(deploy_id) if deploy_id else None,
                container_id=container_id,
                container_name=container_name or "",
                status=ServiceLogStream.Status.ACTIVE,
                started_at=timezone.now(),
            )
    except IntegrityError:
        # Another collector won the active-stream race.
        existing = ServiceLogStream.objects.using(alias).filter(**filters).first()
        if existing:
            return existing
        raise


def close_stream(
    stream: ServiceLogStream,
    *,
    status: str = ServiceLogStream.Status.CLOSED,
    owner_id: str | None = None,
) -> None:
    alias = _alias()
    qs = ServiceLogStream.objects.using(alias).filter(pk=stream.pk)
    if owner_id:
        # A stale collector must never close a stream after its lease is lost.
        qs = qs.filter(owner_id=owner_id)
    qs.update(
        status=status,
        ended_at=timezone.now(),
        owner_id="",
        lease_until=None,
        lease_token="",
        heartbeat_at=None,
        updated_at=timezone.now(),
    )


def _record_drop_locked(
    service_id: str,
    *,
    entries: int,
    bytes_dropped: int,
) -> None:
    """Update drop accounting inside the caller's ServiceLogUsage lock."""
    if entries <= 0 and bytes_dropped <= 0:
        return
    alias = _alias()
    now = timezone.now()
    ServiceLogUsage.objects.using(alias).filter(pk=service_id).update(
        entries_dropped=F("entries_dropped") + max(0, entries),
        bytes_dropped=F("bytes_dropped") + max(0, bytes_dropped),
        updated_at=now,
    )
    day, _ = LogUsageDaily.objects.using(alias).get_or_create(
        service_id=service_id, date=timezone.localdate(), defaults={},
    )
    LogUsageDaily.objects.using(alias).filter(pk=day.pk).update(
        entries_dropped=F("entries_dropped") + max(0, entries),
        bytes_dropped=F("bytes_dropped") + max(0, bytes_dropped),
    )


def _trim_fifo_locked(
    service_id: str,
    usage: ServiceLogUsage,
    need_bytes: int,
    policy: EffectiveLoggingPolicy,
) -> int:
    """Delete oldest rows while the caller holds the service usage row lock."""
    alias = _alias()
    freed = 0
    while int(usage.current_storage_bytes or 0) + need_bytes > policy.storage_quota_bytes:
        rows = list(
            ServiceLogEntry.objects.using(alias)
            .filter(service_id=service_id)
            .order_by("ts", "id")
            .values("id", "byte_size")[:500]
        )
        if not rows:
            break
        ids = [row["id"] for row in rows]
        deleted_count, _ = (
            ServiceLogEntry.objects.using(alias)
            .filter(service_id=service_id, id__in=ids)
            .delete()
        )
        deleted_entries = min(len(rows), int(deleted_count or 0))
        if deleted_entries <= 0:
            break
        removed_bytes = sum(
            int(row.get("byte_size") or 0) for row in rows[:deleted_entries]
        )
        freed += removed_bytes
        usage.current_storage_bytes = max(
            0, int(usage.current_storage_bytes or 0) - removed_bytes
        )
        usage.entry_count = max(0, int(usage.entry_count or 0) - deleted_entries)
        now = timezone.now()
        ServiceLogUsage.objects.using(alias).filter(pk=service_id).update(
            current_storage_bytes=usage.current_storage_bytes,
            entry_count=usage.entry_count,
            updated_at=now,
        )
        day, _ = LogUsageDaily.objects.using(alias).get_or_create(
            service_id=service_id, date=timezone.localdate(), defaults={},
        )
        LogUsageDaily.objects.using(alias).filter(pk=day.pk).update(
            bytes_deleted=F("bytes_deleted") + removed_bytes,
            entries_deleted=F("entries_deleted") + deleted_entries,
        )
    return freed
def _prepare_lines(lines: Iterable[dict], policy: EffectiveLoggingPolicy) -> list[dict]:
    """Normalize, redact, truncate and classify lines before any delivery path."""
    prepared: list[dict] = []
    for raw in lines:
        ts = raw.get("ts") or timezone.now()
        if isinstance(ts, str):
            ts = parse_datetime(ts) or timezone.now()
        if timezone.is_naive(ts):
            ts = timezone.make_aware(ts, timezone.utc)

        stream_kind = (raw.get("stream") or "stdout").lower()
        if stream_kind not in {"stdout", "stderr"}:
            stream_kind = "stdout"

        msg = _redact(str(raw.get("message") or ""))
        truncated = False
        if len(msg.encode("utf-8", "replace")) > policy.max_entry_size:
            encoded = msg.encode("utf-8", "replace")[: policy.max_entry_size]
            msg = encoded.decode("utf-8", "replace") + "…[truncated]"
            truncated = True

        prepared.append(
            {
                "ts": ts,
                "stream": stream_kind,
                "message": msg,
                "fingerprint": fingerprint(ts, stream_kind, msg),
                "byte_size": len(msg.encode("utf-8", "replace")),
                "truncated": truncated,
                "level": infer_level(msg),
            }
        )
    return prepared


def ingest_lines(
    stream: ServiceLogStream,
    lines: Iterable[dict],
    *,
    policy: EffectiveLoggingPolicy | None = None,
    owner_id: str | None = None,
) -> dict:
    """Persist a batch with service-wide atomic quota enforcement."""
    alias = _alias()
    policy = policy or resolve_for_service_id(stream.service_id)
    prepared = _prepare_lines(lines, policy)

    if not policy.persistent_enabled or policy.quota_behavior == "realtime_only":
        return {
            "inserted": 0, "duplicates": 0, "dropped": 0, "bytes": 0,
            "realtime_only": True, "persisted": False,
            "inserted_entries": [], "realtime_lines": prepared,
        }
    if not prepared:
        return {
            "inserted": 0, "duplicates": 0, "dropped": 0, "bytes": 0,
            "persisted": True, "inserted_entries": [],
        }

    service_key = str(stream.service_id)
    inserted_entries: list[dict] = []
    inserted = 0
    total_bytes = 0
    duplicates = 0

    with transaction.atomic(using=alias):
        # One lock shared by all container streams of this service prevents
        # simultaneous batches from making independent quota decisions.
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
        locked = (
            ServiceLogStream.objects.using(alias)
            .select_for_update()
            .filter(pk=stream.pk)
            .first()
        )
        if locked is None:
            return {
                "inserted": 0, "duplicates": 0, "dropped": 0,
                "bytes": 0, "persisted": False, "inserted_entries": [],
            }
        if owner_id and not lease_is_current(locked, owner_id):
            return {
                "inserted": 0, "duplicates": 0, "dropped": 0,
                "bytes": 0, "lease_denied": True,
            }

        # Only new fingerprints reserve storage. Keep all original lines for
        # monotonic sequence allocation and conflict-safe retry semantics.
        unique_by_fingerprint = {}
        for item in prepared:
            unique_by_fingerprint.setdefault(item["fingerprint"], item)
        unique_items = list(unique_by_fingerprint.values())
        existing_fingerprints = set(
            ServiceLogEntry.objects.using(alias)
            .filter(
                stream_id=locked.pk,
                fingerprint__in=[item["fingerprint"] for item in unique_items],
            )
            .values_list("fingerprint", flat=True)
        )
        new_items = [
            item for item in unique_items
            if item["fingerprint"] not in existing_fingerprints
        ]
        need_bytes = sum(int(item["byte_size"] or 0) for item in new_items)

        if (
            need_bytes > 0
            and int(usage.current_storage_bytes or 0) + need_bytes
            > policy.storage_quota_bytes
        ):
            if policy.quota_behavior == "drop_new":
                _record_drop_locked(
                    service_key, entries=len(new_items), bytes_dropped=need_bytes,
                )
                return {
                    "inserted": 0,
                    "duplicates": len(prepared) - len(new_items),
                    "dropped": len(new_items),
                    "dropped_bytes": need_bytes,
                    "bytes": 0,
                    "persisted": False,
                    "inserted_entries": [],
                    "realtime_lines": prepared,
                }

            _trim_fifo_locked(service_key, usage, need_bytes, policy)
            if int(usage.current_storage_bytes or 0) + need_bytes > policy.storage_quota_bytes:
                _record_drop_locked(
                    service_key, entries=len(new_items), bytes_dropped=need_bytes,
                )
                return {
                    "inserted": 0,
                    "duplicates": len(prepared) - len(new_items),
                    "dropped": len(new_items),
                    "dropped_bytes": need_bytes,
                    "bytes": 0,
                    "persisted": False,
                    "inserted_entries": [],
                    "realtime_lines": prepared,
                }

        previous_seq = int(locked.last_seq or 0)
        next_seq = previous_seq
        objects = []
        for item in prepared:
            next_seq += 1
            objects.append(
                ServiceLogEntry(
                    service_id=str(locked.service_id),
                    stream_id=locked.pk,
                    deploy_id=str(locked.deploy_id) if locked.deploy_id else None,
                    ts=item["ts"],
                    seq=next_seq,
                    stream=item["stream"],
                    level=item["level"],
                    message=item["message"],
                    byte_size=item["byte_size"],
                    truncated=item["truncated"],
                    fingerprint=item["fingerprint"],
                )
            )

        ServiceLogEntry.objects.using(alias).bulk_create(
            objects, batch_size=500, ignore_conflicts=True,
        )
        inserted_entries = list(
            ServiceLogEntry.objects.using(alias)
            .filter(stream_id=locked.pk, seq__gt=previous_seq, seq__lte=next_seq)
            .order_by("seq")
            .values(
                "id", "stream_id", "ts", "seq", "stream", "level",
                "message", "byte_size", "truncated",
            )
        )
        inserted = len(inserted_entries)
        duplicates = max(0, len(prepared) - inserted)
        total_bytes = sum(int(item["byte_size"] or 0) for item in inserted_entries)

        latest = max(prepared, key=lambda item: item["ts"])
        now = timezone.now()
        ServiceLogStream.objects.using(alias).filter(pk=locked.pk).update(
            last_seq=next_seq,
            last_persisted_ts=latest["ts"],
            last_persisted_fingerprint=latest["fingerprint"],
            updated_at=now,
        )
        stream.last_seq = next_seq
        stream.last_persisted_ts = latest["ts"]
        stream.last_persisted_fingerprint = latest["fingerprint"]

        if inserted:
            ServiceLogUsage.objects.using(alias).filter(pk=service_key).update(
                current_storage_bytes=F("current_storage_bytes") + total_bytes,
                entry_count=F("entry_count") + inserted,
                last_ingestion_at=now,
                updated_at=now,
            )
            day, _ = LogUsageDaily.objects.using(alias).get_or_create(
                service_id=service_key, date=timezone.localdate(), defaults={},
            )
            LogUsageDaily.objects.using(alias).filter(pk=day.pk).update(
                bytes_ingested=F("bytes_ingested") + total_bytes,
                entries_ingested=F("entries_ingested") + inserted,
            )

    return {
        "inserted": inserted, "duplicates": duplicates, "dropped": 0,
        "bytes": total_bytes, "persisted": True,
        "inserted_entries": inserted_entries,
    }
