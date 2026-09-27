"""Conservative storage capability and real Docker volume usage inspection.

Volume.size_mb is declared logical capacity. It is never treated as physical usage
or proof of a hard storage limit. Docker Engine system-df is used for measurements.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping

CAPACITY_HARD_ENFORCED = "HARD_ENFORCED"
CAPACITY_LOGICAL_ONLY = "LOGICAL_ONLY"
CAPACITY_UNENFORCED = "UNENFORCED"
CAPACITY_UNKNOWN = "UNKNOWN"

USAGE_NORMAL = "normal"
USAGE_WARNING = "warning"
USAGE_CRITICAL = "critical"
USAGE_UNKNOWN = "usage_unavailable"

@dataclass(frozen=True)
class StorageCapabilities:
    supports_usage_reporting: bool
    supports_hard_capacity: bool
    supports_resize: bool
    scope: str
    capacity_mode: str

@dataclass(frozen=True)
class VolumeUsage:
    volume: str
    declared_capacity_bytes: int | None
    actual_used_bytes: int | None
    usage_percent: float | None
    usage_state: str
    threshold_percent: float
    driver: str
    scope: str
    enforced: bool
    capacity_mode: str
    usage_available: bool
    error: str | None = None

def volume_usage_warning_percent() -> float:
    try:
        try:
            from core.settings_service import volume_usage_warning_percent
            value = volume_usage_warning_percent()
        except Exception:
            from django.conf import settings
            value = getattr(settings, "VOLUME_USAGE_WARNING_PERCENT", 90)
    except Exception:
        value = 90
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 90.0
    return max(1.0, min(99.0, value))

def storage_capabilities(driver: str, scope: str | None = None) -> StorageCapabilities:
    normalized = str(driver or "local").strip().lower() or "local"
    normalized_scope = str(scope or "").strip().lower()
    if not normalized_scope:
        normalized_scope = "local" if normalized == "local" else "unknown"
    return StorageCapabilities(
        supports_usage_reporting=True,
        supports_hard_capacity=False,
        supports_resize=False,
        scope="local" if normalized_scope == "local" else normalized_scope,
        capacity_mode=CAPACITY_LOGICAL_ONLY if normalized == "local" else CAPACITY_UNKNOWN,
    )

def _records(raw: Any) -> list[Mapping[str, Any]]:
    if not isinstance(raw, Mapping):
        return []
    records = raw.get("VolumesUsage")
    if records is None:
        records = raw.get("Volumes")
    return [item for item in records if isinstance(item, Mapping)] if isinstance(records, list) else []

def _name(record: Mapping[str, Any]) -> str:
    return str(record.get("Name") or record.get("name") or "").strip()

def _used_bytes(record: Mapping[str, Any]) -> int | None:
    usage = record.get("UsageData") or record.get("Usage")
    value = usage.get("Size") if isinstance(usage, Mapping) else None
    if value is None and isinstance(usage, Mapping):
        value = usage.get("size")
    if value is None:
        value = record.get("Size")
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return None if value < 0 else value

def inspect_volume_usage(client, volume_name: str, declared_mb: int | None, *, threshold_percent: float | None = None) -> VolumeUsage:
    threshold = volume_usage_warning_percent() if threshold_percent is None else max(1.0, min(99.0, float(threshold_percent)))
    declared_bytes = int(declared_mb) * 1024 * 1024 if declared_mb is not None and int(declared_mb) > 0 else None
    try:
        docker_volume = client.volumes.get(volume_name)
        attrs = getattr(docker_volume, "attrs", {}) or {}
        driver = str(attrs.get("Driver") or "local").strip() or "local"
        scope = str(attrs.get("Scope") or "").strip().lower() or ("local" if driver == "local" else "unknown")
        capabilities = storage_capabilities(driver, scope)
    except Exception as exc:
        return VolumeUsage(volume_name, declared_bytes, None, None, USAGE_UNKNOWN, threshold, "unknown", "unknown", False, CAPACITY_UNKNOWN, False, f"{type(exc).__name__}: {exc}")
    try:
        raw = client.df()
        record = next((item for item in _records(raw) if _name(item) == volume_name), None)
        used = _used_bytes(record) if record is not None else None
        if used is None or declared_bytes is None:
            return VolumeUsage(volume_name, declared_bytes, used, None, USAGE_UNKNOWN, threshold, driver, capabilities.scope, capabilities.supports_hard_capacity, capabilities.capacity_mode, used is not None, None if used is not None else "Docker did not provide a measurable usage value.")
        percent = (used / declared_bytes) * 100.0
        state = USAGE_CRITICAL if percent >= 100.0 else USAGE_WARNING if percent >= threshold else USAGE_NORMAL
        return VolumeUsage(volume_name, declared_bytes, used, round(percent, 2), state, threshold, driver, capabilities.scope, capabilities.supports_hard_capacity, capabilities.capacity_mode, True)
    except Exception as exc:
        return VolumeUsage(volume_name, declared_bytes, None, None, USAGE_UNKNOWN, threshold, driver, capabilities.scope, capabilities.supports_hard_capacity, capabilities.capacity_mode, False, f"{type(exc).__name__}: {exc}")

def usage_details(usage: VolumeUsage) -> dict[str, Any]:
    mb = 1024 * 1024
    return {
        "volume": usage.volume,
        "declared_mb": round(usage.declared_capacity_bytes / mb, 2) if usage.declared_capacity_bytes is not None else None,
        "used_bytes": usage.actual_used_bytes,
        "used_mb": round(usage.actual_used_bytes / mb, 2) if usage.actual_used_bytes is not None else None,
        "usage_percent": usage.usage_percent,
        "threshold_percent": usage.threshold_percent,
        "usage_state": usage.usage_state,
        "driver": usage.driver,
        "scope": usage.scope,
        "enforced": usage.enforced,
        "capacity_mode": usage.capacity_mode,
        "usage_available": usage.usage_available,
        "error": usage.error,
    }

def reconcile_managed_volumes(client) -> dict[str, list[dict[str, Any]]]:
    """Compare managed Docker volumes on the connected node with the Django registry.

    This is deliberately read-only. For node-local Docker storage, the result
    describes only the connected Docker daemon; remote Swarm workers require
    the same check through a Docker client connected to those nodes.
    """
    try:
        docker_rows = client.volumes.list(filters={"label": "managed-by=django-paas-deployer"})
    except Exception as exc:
        return {
            "docker_orphans": [],
            "missing_docker": [],
            "error": [
                {"exception_type": type(exc).__name__, "error": str(exc)}
            ],
        }
    docker_names = {
        str(getattr(row, "name", "") or getattr(row, "attrs", {}).get("Name") or "").strip()
        for row in docker_rows
    }
    docker_names.discard("")
    try:
        from services.models import Volume as RegistryVolume
        registry_rows = list(
            RegistryVolume.objects.values("id", "name", "service_id", "size_mb")
        )
    except Exception as exc:
        return {
            "docker_orphans": [],
            "missing_docker": [],
            "error": [
                {"exception_type": type(exc).__name__, "error": str(exc)}
            ],
        }
    expected = {}
    for row in registry_rows:
        volume_id = str(row["id"])
        expected_name = f"vol-{volume_id.replace('-', '')[:8]}-{row['name']}"
        expected[expected_name] = row
    return {
        "docker_orphans": [
            {"volume": name, "scope": "connected_node"}
            for name in sorted(docker_names - set(expected))
        ],
        "missing_docker": [
            {
                "volume": name,
                "service_id": str(row["service_id"]) if row["service_id"] else None,
                "declared_mb": row["size_mb"],
                "scope": "connected_node",
            }
            for name, row in sorted(expected.items())
            if name not in docker_names
        ],
        "error": [],
    }
