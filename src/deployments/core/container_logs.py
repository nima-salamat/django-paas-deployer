"""
deployments/core/container_logs.py
----------------------------------
Capture container-internal logs before forced removal during deploy
and persist them as DeployLog rows with a clear label.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def capture_logs_for_deploy(
    container_name: str,
    *,
    deploy_id: Any,
    stage: str = "container_logs",
    tail: int = 500,
    reason: str = "",
    service_id: Optional[Any] = None,
) -> str:
    """
    Best-effort: read Docker logs for ``container_name``, redact secrets,
    and write a DeployLog row marked as internal container logs.

    Returns the (possibly empty) log text.  Never raises to the caller
    so cleanup paths remain safe.
    """
    text = ""
    exit_code = None
    status = "unknown"

    try:
        from deployments.core.manager.container_manager import Container
        from deployments.common.security import redact_secrets

        c = Container(container_name)
        info = c.inspect() or {}
        state = info.get("State") or {}
        status = (state.get("Status") or status) or "unknown"
        exit_code = state.get("ExitCode")

        client = c.client
        try:
            raw = client.api.logs(container_name, tail=tail, timestamps=True)
            text = (
                raw.decode("utf-8", "replace")
                if isinstance(raw, (bytes, bytearray))
                else str(raw or "")
            )
        except Exception:
            try:
                cont = client.containers.get(container_name)
                raw = cont.logs(tail=tail, timestamps=True)
                text = (
                    raw.decode("utf-8", "replace")
                    if isinstance(raw, (bytes, bytearray))
                    else str(raw or "")
                )
            except Exception:
                pass

        text = redact_secrets(text)
    except Exception as exc:
        logger.debug(
            "capture_logs_for_deploy: could not read logs for %s: %s",
            container_name,
            exc,
        )

    try:
        from django.conf import settings  # type: ignore
        from deploy.models import DeployLog  # type: ignore

        alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"
        msg = (
            f"Internal container logs captured before removal of "
            f"'{container_name}'."
        )
        if reason:
            msg = f"{msg} Reason: {reason}"

        kwargs = {
            "deploy_id": deploy_id,
            "stage": (stage or "container_logs")[:64],
            "event_type": "deployment.container_logs",
            "level": "error" if reason else "warning",
            "message": msg[:4000],
            "details": {
                "source": "container_logs",
                "label": "container_internal_logs",
                "container": container_name,
                "status": status,
                "exit_code": exit_code,
                "reason": reason or "",
                "logs": text,
            },
        }
        if service_id is not None:
            kwargs["service_id"] = service_id

        DeployLog.objects.using(alias).create(**kwargs)
        logger.info(
            "Persisted container-internal logs for deploy=%s container=%s "
            "(%d chars)",
            deploy_id,
            container_name,
            len(text),
        )
    except Exception:
        logger.exception(
            "Failed to persist container logs for deploy %s container=%s",
            deploy_id,
            container_name,
        )

    return text


__all__ = ["capture_logs_for_deploy"]
