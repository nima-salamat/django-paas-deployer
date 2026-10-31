from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="logs.retain_all_services")
def retain_all_services():
    """Run retention for every service without a hard 5,000-service ceiling."""
    from django.conf import settings
    from logs.models import ServiceLogUsage
    from logs.retention import retain_service

    alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", "default")
    total = 0
    scanned = 0
    after_service_id = None
    while True:
        qs = ServiceLogUsage.objects.using(alias).order_by("service_id")
        if after_service_id is not None:
            qs = qs.filter(service_id__gt=after_service_id)
        batch = list(qs.values_list("service_id", flat=True)[:200])
        if not batch:
            break

        for sid in batch:
            scanned += 1
            try:
                result = retain_service(sid)
                total += int(result.get("deleted") or 0)
            except Exception:
                logger.exception("retain failed service=%s", sid)
        after_service_id = batch[-1]

    return {"deleted": total, "services_scanned": scanned}


@shared_task(name="logs.reconcile_usage")
def reconcile_usage(limit: int = 200):
    """Reconcile every service in bounded pages, not only the first page."""
    from django.conf import settings
    from django.db.models import Count, Sum
    from logs.models import ServiceLogEntry, ServiceLogUsage

    alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", "default")
    chunk_size = max(1, min(int(limit or 200), 1000))
    fixed = 0
    scanned = 0
    after_service_id = None

    while True:
        qs = ServiceLogUsage.objects.using(alias).order_by("service_id")
        if after_service_id is not None:
            qs = qs.filter(service_id__gt=after_service_id)
        batch = list(qs[:chunk_size])
        if not batch:
            break

        service_ids = [row.service_id for row in batch]
        aggregates = (
            ServiceLogEntry.objects.using(alias)
            .filter(service_id__in=service_ids)
            .values("service_id")
            .annotate(c=Count("id"), b=Sum("byte_size"))
        )
        by_service = {row["service_id"]: row for row in aggregates}
        changed = []
        for usage in batch:
            aggregate = by_service.get(usage.service_id) or {}
            count = int(aggregate.get("c") or 0)
            byte_count = int(aggregate.get("b") or 0)
            if (
                count != int(usage.entry_count or 0)
                or byte_count != int(usage.current_storage_bytes or 0)
            ):
                usage.entry_count = count
                usage.current_storage_bytes = byte_count
                changed.append(usage)

        if changed:
            ServiceLogUsage.objects.using(alias).bulk_update(
                changed, ["entry_count", "current_storage_bytes"],
                batch_size=chunk_size,
            )
            fixed += len(changed)
        scanned += len(batch)
        after_service_id = batch[-1].service_id

    return {"fixed": fixed, "services_scanned": scanned}
