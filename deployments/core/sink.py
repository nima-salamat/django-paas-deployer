from __future__ import annotations

import logging
import time
from typing import Any, Optional

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.utils import timezone

from deploy.models import Deploy, DeployLog, DeploymentStatusChoices

from .types import DeploymentEvent

logger = logging.getLogger(__name__)


def _log_db_alias() -> str:
    return getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"


def _serialize_event(event: DeploymentEvent | dict) -> dict[str, Any]:
    if isinstance(event, dict):
        return {
            "stage": event.get("stage", "") or "",
            "message": (event.get("message") or "")[:4000],
            "level": (event.get("level") or "info").lower(),
            "progress": event.get("progress"),
            "details": event.get("details") or {},
            "timestamp": event.get("timestamp") or timezone.now().isoformat(),
        }
    return {
        "stage": event.stage or "",
        "message": (event.message or "")[:4000],
        "level": (event.level or "info").lower(),
        "progress": event.progress,
        "details": event.details or {},
        "timestamp": timezone.now().isoformat(),
    }


# Docker build stream lines that are pure noise for the UI / DeployLog.
_NOISE_BUILD_PREFIXES = (
    " --->",
    "--->",
    "removing intermediate",
    "step ",
    "[warning] one or more build-args",
)


def _is_noisy_build_line(stage: str, message: str, level: str) -> bool:
    """True when the event is a low-value docker build stream line."""
    if (stage or "").lower() != "image_build":
        return False
    if (level or "").lower() in ("error", "warning"):
        return False
    msg = (message or "").strip().lower()
    if not msg:
        return True
    if msg.startswith(_NOISE_BUILD_PREFIXES):
        return True
    # Keep milestone lines
    keep = (
        "successfully built",
        "successfully tagged",
        "writing image",
        "docker image built",
        "pulling",
        "already exists",
        "error",
        "failed",
    )
    if any(k in msg for k in keep):
        return False
    # Long RUN output without keywords → noise
    if len(msg) > 200 and not any(k in msg for k in ("error", "fail", "success")):
        return True
    return False


class DBAndChannelEventSink:
    """
    Primary event sink used by DeploymentLogger / Orchestrator / DBDeployer.

    Responsibilities (always best-effort, never abort the deploy pipeline):
      1. Persist DeployLog (cross-DB safe via raw FKs)
      2. Keep Deploy.progress / stage / status_message in sync
      3. Broadcast to Channels group ``deploy_<id>`` → DeploymentConsumer

    Usage::

        sink = DBAndChannelEventSink(deploy.pk)
        sink(DeploymentEvent(stage="image_build", message="…", progress=25))
    """

    _SUCCESS_STAGES = frozenset({
        "deployment_completed",
        "finished",
        "rollback_completed",
    })
    _FAILURE_STAGES = frozenset({
        "deployment_failed",
        "validation",
        "health_check",
        "timeout",
        "rollback_failed",
        "cancelled",
        "volume",
        "container_creation",
        "container_startup",
        "image_pull",
    })

    # Throttle noisy image_build stream to WS (still may persist selectively)
    _WS_MIN_INTERVAL_SEC = 0.35

    def __init__(self, deployment_id):
        self.deployment_id = str(deployment_id)
        self._deploy_cache: Optional[Deploy] = None
        self._group_name = f"deploy_{self.deployment_id}"
        self._last_ws_at: float = 0.0
        self._last_ws_message: str = ""
        self._last_progress: Optional[int] = None

    def __call__(self, event: DeploymentEvent | dict) -> None:
        payload = _serialize_event(event)
        stage = payload.get("stage") or ""
        message = payload.get("message") or ""
        level = payload.get("level") or "info"
        noisy = _is_noisy_build_line(stage, message, level)

        # Always persist non-noise; for noise only persist errors/warnings
        if not noisy or level in ("error", "warning"):
            self._write_deploy_log(payload)

        # Always keep Deploy row in sync for progress / stage transitions
        self._update_deploy_row(payload, skip_message=noisy and level == "info")

        # Broadcast: skip pure noise, throttle remaining build spam
        if noisy:
            return
        self._broadcast(payload)

    def record(self, event: DeploymentEvent | dict) -> None:
        self(event)

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------

    def _write_deploy_log(self, payload: dict) -> None:
        try:
            service_id = None
            try:
                deploy = self._get_deploy()
                service_id = getattr(deploy, "service_id", None) or (
                    deploy.service.pk if getattr(deploy, "service", None) else None
                )
            except Exception:
                pass

            DeployLog.objects.using(_log_db_alias()).create(
                deploy_id=self.deployment_id,
                service_id=service_id,
                stage=(payload.get("stage") or "unknown")[:64],
                event_type="deployment.live",
                level=payload.get("level") or "info",
                message=(payload.get("message") or "")[:4000],
                progress=payload.get("progress"),
                details=payload.get("details") or {},
            )
        except Exception:
            logger.exception(
                "Failed to write DeployLog for deploy %s stage=%s",
                self.deployment_id,
                payload.get("stage"),
            )

    def _update_deploy_row(self, payload: dict, *, skip_message: bool = False) -> None:
        try:
            progress = payload.get("progress")
            stage = payload.get("stage") or ""
            message = payload.get("message") or ""
            level = (payload.get("level") or "info").lower()

            update_fields: dict[str, Any] = {}
            if progress is not None:
                try:
                    p = int(progress)
                    update_fields["progress"] = max(0, min(100, p))
                except (TypeError, ValueError):
                    pass
            if stage:
                update_fields["stage"] = stage[:64]
            if message and not skip_message:
                update_fields["status_message"] = message[:500]

            if stage in self._SUCCESS_STAGES and progress == 100:
                update_fields.setdefault("status", DeploymentStatusChoices.SUCCEEDED)
                update_fields.setdefault("completed_at", timezone.now())
            elif level == "error" and stage in self._FAILURE_STAGES:
                update_fields.setdefault("error_message", message[:1000])

            if update_fields:
                Deploy.objects.filter(pk=self.deployment_id).update(**update_fields)
        except Exception:
            logger.exception(
                "Failed to update Deploy row for %s", self.deployment_id
            )

    # ------------------------------------------------------------------
    # WebSocket broadcast
    # ------------------------------------------------------------------

    def _broadcast(self, payload: dict) -> None:
        """
        Push to Channels group joined by DeploymentConsumer.

        Channel type must be ``deployment.message`` → handler ``deployment_message``.
        Throttles identical rapid messages so the UI stays responsive.
        """
        try:
            now = time.monotonic()
            msg = payload.get("message") or ""
            progress = payload.get("progress")
            level = (payload.get("level") or "info").lower()

            # Always send errors / terminal progress immediately
            force = level in ("error", "warning") or progress in (0, 100) or (
                payload.get("stage") or ""
            ) in self._SUCCESS_STAGES | self._FAILURE_STAGES | {
                "deployment_started",
                "container_startup",
                "health_check",
                "deployment_completed",
                "deployment_failed",
            }

            if not force:
                if msg == self._last_ws_message and progress == self._last_progress:
                    return
                if (now - self._last_ws_at) < self._WS_MIN_INTERVAL_SEC:
                    return

            self._last_ws_at = now
            self._last_ws_message = msg
            self._last_progress = progress

            channel_layer = get_channel_layer()
            if channel_layer is None:
                logger.warning(
                    "No channel layer configured; WS broadcast skipped for deploy %s",
                    self.deployment_id,
                )
                return

            async_to_sync(channel_layer.group_send)(
                self._group_name,
                {
                    "type": "deployment.message",
                    "payload": {
                        "deploy_id": self.deployment_id,
                        "stage": payload.get("stage"),
                        "message": payload.get("message"),
                        "level": payload.get("level"),
                        "progress": payload.get("progress"),
                        "details": payload.get("details") or {},
                        "timestamp": payload.get("timestamp"),
                    },
                },
            )
        except Exception:
            logger.exception(
                "Channel broadcast failed for deploy %s group=%s",
                self.deployment_id,
                self._group_name,
            )

    def _get_deploy(self) -> Deploy:
        if self._deploy_cache is None:
            self._deploy_cache = Deploy.objects.select_related("service").get(
                pk=self.deployment_id
            )
        return self._deploy_cache


class DeploymentEventPipeline(DBAndChannelEventSink):
    """Alias kept for older imports of ``deploy.event_pipeline``."""

    pass
