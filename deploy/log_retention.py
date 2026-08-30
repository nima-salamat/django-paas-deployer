"""
Retain at most MAX_LOGS_PER_SERVICE DeployLog rows per service (FIFO).

DeployLog may live on a separate DB alias (DEPLOYMENT_LOG_DB_ALIAS).
"""
from __future__ import annotations

import logging
from django.conf import settings

logger = logging.getLogger(__name__)

MAX_LOGS_PER_SERVICE = 10000


def _alias() -> str:
    return getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"


def trim_service_logs(service_id, *, keep: int = MAX_LOGS_PER_SERVICE) -> int:
    """
    Delete oldest DeployLog rows for service so at most `keep` remain.
    Returns number of rows deleted.
    """
    if service_id is None or keep < 1:
        return 0
    from .models import DeployLog

    alias = _alias()
    try:
        qs = (
            DeployLog.objects.using(alias)
            .filter(service_id=service_id)
            .order_by("-created_at")
        )
        # ids to keep = newest `keep`
        keep_ids = list(qs.values_list("pk", flat=True)[:keep])
        if not keep_ids:
            return 0
        # Count total cheaply
        total = (
            DeployLog.objects.using(alias).filter(service_id=service_id).count()
        )
        if total <= keep:
            return 0
        deleted, _ = (
            DeployLog.objects.using(alias)
            .filter(service_id=service_id)
            .exclude(pk__in=keep_ids)
            .delete()
        )
        if deleted:
            logger.info(
                "DeployLog retention: service=%s deleted=%s keep=%s",
                service_id,
                deleted,
                keep,
            )
        return int(deleted or 0)
    except Exception:
        logger.exception("DeployLog retention failed for service=%s", service_id)
        return 0


def trim_after_write(service_id) -> None:
    """Best-effort trim after inserting a log row."""
    try:
        trim_service_logs(service_id)
    except Exception:
        logger.debug("trim_after_write failed", exc_info=True)
