"""Single source of truth for EffectiveLoggingPolicy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class EffectiveLoggingPolicy:
    retention_days: int
    storage_quota_bytes: int
    max_bytes_per_second: int
    max_entry_size: int
    persistent_enabled: bool
    realtime_enabled: bool
    quota_behavior: str  # fifo_delete | drop_new | realtime_only


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(int(value), high))


def resolve(service) -> EffectiveLoggingPolicy:
    """
    Platform SystemSetting defaults + Plan caps, clamped to platform maxima.
    """
    from core.settings_service import get_bool, get_int, get_str

    platform_max_retention = max(1, get_int("logging.platform_max_retention_days", 90))
    platform_max_storage_mb = max(1, get_int("logging.platform_max_storage_mb_per_service", 5120))
    platform_max_bps = max(1024, get_int("logging.platform_max_ingest_bytes_per_sec", 1_048_576))
    default_retention = _clamp(get_int("logging.default_retention_days", 14), 1, platform_max_retention)
    default_storage_mb = _clamp(get_int("logging.default_storage_mb_per_service", 512), 1, platform_max_storage_mb)
    default_bps = _clamp(get_int("logging.default_ingest_bytes_per_sec", 262_144), 1024, platform_max_bps)
    max_entry = _clamp(get_int("logging.max_entry_size", 16_384), 256, 1_048_576)
    persistent = get_bool("logging.persistent_enabled", True)
    realtime = get_bool("logging.realtime_enabled", True)
    quota_behavior = (get_str("logging.default_quota_behavior", "fifo_delete") or "fifo_delete").strip().lower()
    if quota_behavior not in {"fifo_delete", "drop_new", "realtime_only"}:
        quota_behavior = "fifo_delete"

    plan = getattr(service, "plan", None)
    if plan is not None:
        pr = getattr(plan, "log_retention_days", None)
        if pr is not None:
            default_retention = _clamp(int(pr), 1, platform_max_retention)
        ps = getattr(plan, "log_storage_mb", None)
        if ps is not None:
            default_storage_mb = _clamp(int(ps), 1, platform_max_storage_mb)
        pb = getattr(plan, "log_ingest_bytes_per_sec", None)
        if pb is not None:
            default_bps = _clamp(int(pb), 1024, platform_max_bps)
        if getattr(plan, "persistent_logging", None) is not None:
            persistent = bool(plan.persistent_logging) and persistent
        if getattr(plan, "realtime_logging", None) is not None:
            realtime = bool(plan.realtime_logging) and realtime
        qb = getattr(plan, "log_quota_behavior", None)
        if qb:
            qb = str(qb).strip().lower()
            if qb in {"fifo_delete", "drop_new", "realtime_only"}:
                quota_behavior = qb

    return EffectiveLoggingPolicy(
        retention_days=default_retention,
        storage_quota_bytes=default_storage_mb * 1024 * 1024,
        max_bytes_per_second=default_bps,
        max_entry_size=max_entry,
        persistent_enabled=bool(persistent),
        realtime_enabled=bool(realtime),
        quota_behavior=quota_behavior,
    )


def resolve_for_service_id(service_id: UUID | str) -> EffectiveLoggingPolicy:
    from services.models import Service

    service = Service.objects.select_related("plan").filter(pk=service_id).first()
    if service is None:
        # Platform-only defaults when service missing
        class _S:
            plan = None

        return resolve(_S())
    return resolve(service)
