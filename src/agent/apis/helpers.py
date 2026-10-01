"""Serialization helpers for the modular Agent API."""
from __future__ import annotations

from ..application import deployment_payload, service_payload


class _ServiceSerializer:
    def __init__(self, instance, many=False):
        self.data = [service_payload(x) for x in instance] if many else service_payload(instance)


class _PlanSerializer:
    def __init__(self, instance, many=False):
        self.data = [_plan_payload(x) for x in instance] if many else _plan_payload(instance)


class _NetworkSerializer:
    def __init__(self, instance, many=False):
        self.data = [_network_payload(x) for x in instance] if many else _network_payload(instance)


class _VolumeSerializer:
    def __init__(self, instance, many=False):
        self.data = [_volume_payload(x) for x in instance] if many else _volume_payload(instance)


class _DeploymentSerializer:
    def __init__(self, instance, many=False):
        self.data = [deployment_payload(x) for x in instance] if many else deployment_payload(instance)


def _plan_payload(p):
    return {
        "id": str(p.pk),
        "name": p.name,
        "platform": p.platform,
        "plan_type": p.plan_type,
        "max_cpu": p.max_cpu,
        "max_ram": p.max_ram,
        "max_storage": p.max_storage,
        "storage_type": p.storage_type,
        "price_per_hour": p.price_per_hour,
        "price_per_day": p.price_per_day,
        "price_per_month": p.price_per_month,
        "logging": {
            "retention_days": p.log_retention_days,
            "storage_mb": p.log_storage_mb,
            "persistent": p.persistent_logging,
            "realtime": p.realtime_logging,
        },
    }


def _network_payload(n):
    return {
        "id": str(n.pk),
        "name": n.name,
        "description": n.description,
        "created_at": n.created_at,
        "updated_at": n.updated_at,
    }


def _volume_payload(v):
    return {
        "id": str(v.pk),
        "name": v.name,
        "service_id": str(v.service_id) if v.service_id else None,
        "user_id": str(v.user_id),
        "size_mb": v.size_mb,
        "default_bind": v.default_bind,
        "default_mode": v.default_mode,
        "released_at": getattr(v, "released_at", None),
        "reclaim_attempted_at": getattr(v, "reclaim_attempted_at", None),
        "reclaim_error": getattr(v, "reclaim_error", ""),
    }
