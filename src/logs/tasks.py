
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="logs.retain_all_services")
def retain_all_services():
    from django.conf import settings
    from logs.models import ServiceLogUsage
    from logs.retention import retain_service

    alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", "default")
    ids = list(ServiceLogUsage.objects.using(alias).values_list("service_id", flat=True)[:5000])
    total = 0
    for sid in ids:
        try:
            result = retain_service(sid)
            total += int(result.get("deleted") or 0)
        except Exception:
            logger.exception("retain failed service=%s", sid)
    return {"deleted": total}


@shared_task(name="logs.reconcile_usage")
def reconcile_usage(limit: int = 200):
    """Bounded reconcile of ServiceLogUsage vs entry aggregates."""
    from django.conf import settings
    from django.db.models import Count, Sum
    from logs.models import ServiceLogEntry, ServiceLogUsage

    alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", "default")
    fixed = 0
    for u in ServiceLogUsage.objects.using(alias).all()[:limit]:
        agg = (
            ServiceLogEntry.objects.using(alias)
            .filter(service_id=u.service_id)
            .aggregate(c=Count("id"), b=Sum("byte_size"))
        )
        c = int(agg["c"] or 0)
        b = int(agg["b"] or 0)
        if c != int(u.entry_count or 0) or b != int(u.current_storage_bytes or 0):
            ServiceLogUsage.objects.using(alias).filter(pk=u.service_id).update(
                entry_count=c,
                current_storage_bytes=b,
            )
            fixed += 1
    return {"fixed": fixed}
