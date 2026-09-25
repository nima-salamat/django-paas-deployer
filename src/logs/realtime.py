"""Channels helpers for runtime log fanout."""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def group_name(service_id: UUID | str) -> str:
    return f"service.{service_id}.logs"


def publish_log_events(service_id: UUID | str, events: list[dict[str, Any]]) -> None:
    if not events:
        return
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            group_name(service_id),
            {"type": "runtime.log.batch", "events": events},
        )
    except Exception:
        logger.debug("runtime log channel publish failed service=%s", service_id, exc_info=True)
