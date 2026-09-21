"""Staff-facing logging health / usage summary."""
from __future__ import annotations

import logging

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

logger = logging.getLogger(__name__)


def _alias():
    return getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"


def _redis_ok() -> bool:
    try:
        from django.core.cache import cache

        cache.set("logging_health_ping", "1", 5)
        return cache.get("logging_health_ping") == "1"
    except Exception:
        return False


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated, IsAdminUser])
def logging_health_apiview(request):
    """
    Bounded operational snapshot. Never returns log line content.
    Degrades gracefully when log DB / Redis / collectors are unavailable.
    """
    alias = _alias()
    db_ok = True
    collectors = []
    total = {"storage": 0, "entries": 0, "dropped": 0}
    top = []
    try:
        from .models import CollectorHeartbeat, ServiceLogUsage

        collectors = list(
            CollectorHeartbeat.objects.using(alias)
            .order_by("-last_heartbeat")[:20]
            .values(
                "instance_id",
                "status",
                "last_heartbeat",
                "last_successful_ingestion",
                "active_streams",
                "active_containers",
                "buffer_bytes",
                "dropped_entries",
                "dropped_bytes",
                "last_error",
                "db_ok",
                "redis_ok",
            )
        )
        total = ServiceLogUsage.objects.using(alias).aggregate(
            storage=Sum("current_storage_bytes"),
            entries=Sum("entry_count"),
            dropped=Sum("entries_dropped"),
        )
        top = list(
            ServiceLogUsage.objects.using(alias)
            .order_by("-current_storage_bytes")[:20]
            .values(
                "service_id",
                "current_storage_bytes",
                "entry_count",
                "entries_dropped",
                "last_ingestion_at",
            )
        )
    except Exception as exc:
        db_ok = False
        logger.warning("logging health log-db unavailable: %s", exc)

    redis_ok = _redis_ok()
    overall = "healthy"
    if not db_ok:
        overall = "disconnected"
    elif not collectors:
        overall = "degraded"
    elif any((c.get("status") or "") not in {"healthy", ""} for c in collectors):
        overall = "degraded"
    elif not redis_ok:
        overall = "degraded"

    lag_seconds = None
    if collectors and collectors[0].get("last_successful_ingestion"):
        try:
            lag_seconds = max(
                0.0,
                (timezone.now() - collectors[0]["last_successful_ingestion"]).total_seconds(),
            )
        except Exception:
            lag_seconds = None

    return Response(
        {
            "result": "success",
            "overall_status": overall,
            "db_ok": db_ok,
            "redis_ok": redis_ok,
            "ingestion_lag_seconds": lag_seconds,
            "collectors": collectors,
            "totals": total or {"storage": 0, "entries": 0, "dropped": 0},
            "top_services_by_storage": top,
            "retention_task": "logs.retain_all_services",
            "reconcile_task": "logs.reconcile_usage",
        }
    )
