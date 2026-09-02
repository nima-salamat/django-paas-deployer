"""Idempotent runtime log ingestion with checkpoints, quota, rate awareness."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Iterable
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import ServiceLogEntry, ServiceLogStream
from .policy import EffectiveLoggingPolicy, resolve_for_service_id
from .usage import bump_delete, bump_drop, bump_ingest, get_usage

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
    try:
        from deployments.common.security import redact_secrets

        return redact_secrets(text or "")
    except Exception:
        return text or ""


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
    existing = (
        ServiceLogStream.objects.using(alias)
        .filter(container_id=container_id, status=ServiceLogStream.Status.ACTIVE)
        .first()
    )
    if existing:
        return existing
    return ServiceLogStream.objects.using(alias).create(
        service_id=str(service_id),
        deploy_id=str(deploy_id) if deploy_id else None,
        container_id=container_id,
        container_name=container_name or "",
        status=ServiceLogStream.Status.ACTIVE,
        started_at=timezone.now(),
    )


def close_stream(stream: ServiceLogStream, *, status: str = ServiceLogStream.Status.CLOSED) -> None:
    alias = _alias()
    ServiceLogStream.objects.using(alias).filter(pk=stream.pk).update(
        status=status,
        ended_at=timezone.now(),
        owner_id="",
        lease_until=None,
        updated_at=timezone.now(),
    )


def _trim_fifo(service_id: str, need_bytes: int, policy: EffectiveLoggingPolicy) -> int:
    """Delete oldest entries until under quota - need_bytes. Returns bytes freed."""
    alias = _alias()
    usage = get_usage(service_id)
    target = max(0, policy.storage_quota_bytes - need_bytes)
    if usage["current_storage_bytes"] <= target:
        return 0
    freed = 0
    deleted = 0
    while usage["current_storage_bytes"] - freed > target:
        batch = list(
            ServiceLogEntry.objects.using(alias)
            .filter(service_id=service_id)
            .order_by("ts", "seq")[:500]
        )
        if not batch:
            break
        ids = [e.id for e in batch]
        batch_bytes = sum(int(e.byte_size or 0) for e in batch)
        ServiceLogEntry.objects.using(alias).filter(id__in=ids).delete()
        freed += batch_bytes
        deleted += len(ids)
        if len(batch) < 500:
            break
    if deleted:
        bump_delete(service_id, bytes_removed=freed, entries=deleted)
    return freed


def ingest_lines(
    stream: ServiceLogStream,
    lines: Iterable[dict],
    *,
    policy: EffectiveLoggingPolicy | None = None,
    owner_id: str | None = None,
) -> dict:
    """
    Ingest normalized lines: {ts, stream, message}.
    Returns counts: inserted, duplicates, dropped, bytes.
    """
    alias = _alias()
    policy = policy or resolve_for_service_id(stream.service_id)
    if not policy.persistent_enabled or policy.quota_behavior == "realtime_only":
        return {"inserted": 0, "duplicates": 0, "dropped": 0, "bytes": 0, "realtime_only": True}

    if owner_id and stream.owner_id and stream.owner_id != owner_id:
        if stream.lease_until and stream.lease_until > timezone.now():
            return {"inserted": 0, "duplicates": 0, "dropped": 0, "bytes": 0, "lease_denied": True}

    inserted = 0
    duplicates = 0
    dropped = 0
    total_bytes = 0
    last_ts = stream.last_persisted_ts
    last_fp = stream.last_persisted_fingerprint or ""
    next_seq = int(stream.last_seq or 0)

    prepared = []
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
            # Truncate by bytes approximately
            encoded = msg.encode("utf-8", "replace")[: policy.max_entry_size]
            msg = encoded.decode("utf-8", "replace") + "…[truncated]"
            truncated = True
        fp = fingerprint(ts, stream_kind, msg)
        size = len(msg.encode("utf-8", "replace"))
        prepared.append(
            {
                "ts": ts,
                "stream": stream_kind,
                "message": msg,
                "fingerprint": fp,
                "byte_size": size,
                "truncated": truncated,
                "level": infer_level(msg),
            }
        )

    if not prepared:
        return {"inserted": 0, "duplicates": 0, "dropped": 0, "bytes": 0}

    need = sum(p["byte_size"] for p in prepared)
    usage = get_usage(stream.service_id)
    if usage["current_storage_bytes"] + need > policy.storage_quota_bytes:
        if policy.quota_behavior == "drop_new":
            bump_drop(stream.service_id, entries=len(prepared), bytes_dropped=need)
            return {"inserted": 0, "duplicates": 0, "dropped": len(prepared), "bytes": 0}
        _trim_fifo(str(stream.service_id), need, policy)

    with transaction.atomic(using=alias):
        locked = (
            ServiceLogStream.objects.using(alias)
            .select_for_update()
            .filter(pk=stream.pk)
            .first()
        )
        if locked is None:
            return {"inserted": 0, "duplicates": 0, "dropped": 0, "bytes": 0}
        next_seq = int(locked.last_seq or 0)
        for p in prepared:
            next_seq += 1
            try:
                ServiceLogEntry.objects.using(alias).create(
                    service_id=str(stream.service_id),
                    stream_id=stream.pk,
                    deploy_id=str(stream.deploy_id) if stream.deploy_id else None,
                    ts=p["ts"],
                    seq=next_seq,
                    stream=p["stream"],
                    level=p["level"],
                    message=p["message"],
                    byte_size=p["byte_size"],
                    truncated=p["truncated"],
                    fingerprint=p["fingerprint"],
                )
                inserted += 1
                total_bytes += p["byte_size"]
                last_ts = p["ts"]
                last_fp = p["fingerprint"]
            except IntegrityError:
                next_seq -= 1  # roll back seq for dup fingerprint
                duplicates += 1
                continue
        ServiceLogStream.objects.using(alias).filter(pk=stream.pk).update(
            last_seq=next_seq,
            last_persisted_ts=last_ts,
            last_persisted_fingerprint=last_fp,
            updated_at=timezone.now(),
        )
        stream.last_seq = next_seq
        stream.last_persisted_ts = last_ts
        stream.last_persisted_fingerprint = last_fp

    if inserted:
        bump_ingest(stream.service_id, bytes_added=total_bytes, entries=inserted)

    return {
        "inserted": inserted,
        "duplicates": duplicates,
        "dropped": dropped,
        "bytes": total_bytes,
    }
