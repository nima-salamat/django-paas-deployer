from __future__ import annotations

import logging
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
            "stage": event.get("stage", ""),
            "message": event.get("message", ""),
            "level": event.get("level", "info"),
            "progress": event.get("progress"),
            "details": event.get("details") or {},
            "timestamp": event.get("timestamp") or timezone.now().isoformat(),
        }
    return {
        "stage": event.stage,
        "message": event.message,
        "level": event.level,
        "progress": event.progress,
        "details": event.details or {},
        "timestamp": timezone.now().isoformat(),
    }


class DBAndChannelEventSink:
    """
    Primary event sink used by DeploymentLogger / Orchestrator / DBDeployer.

    Usage::

        sink = DBAndChannelEventSink(deploy.pk)
        sink(DeploymentEvent(stage="image_build", message="…", progress=25))
    """

    # Stages that mean the deploy is finished (success path)
    _SUCCESS_STAGES = frozenset({
        "deployment_completed",
        "finished",
        "rollback_completed",
    })
    # Stages that mean failure
    _FAILURE_STAGES = frozenset({
        "deployment_failed",
        "image_build",
        "validation",
        "health_check",
        "timeout",
        "rollback_failed",
        "cancelled",
    })

    def __init__(self, deployment_id):
        self.deployment_id = str(deployment_id)
        self._deploy_cache: Optional[Deploy] = None
        self._group_name = f"deploy_{self.deployment_id}"

    # ------------------------------------------------------------------
    # Public callable interface (EventSink protocol)
    # ------------------------------------------------------------------

    def __call__(self, event: DeploymentEvent | dict) -> None:
        payload = _serialize_event(event)
        self._write_deploy_log(payload)
        self._update_deploy_row(payload)
        self._broadcast(payload)

    # Alias used by some callers
    def record(self, event: DeploymentEvent | dict) -> None:
        self(event)

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------

    def _write_deploy_log(self, payload: dict) -> None:
        """
        Write to DeployLog using raw IDs so multi-DB routers never complain.
        Failures are logged but never abort the deployment pipeline.
        """
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
                stage=payload["stage"] or "unknown",
                event_type="deployment.live",
                level=payload.get("level") or "info",
                message=payload.get("message") or "",
                progress=payload.get("progress"),
                details=payload.get("details") or {},
            )
        except Exception:
            logger.exception(
                "Failed to write DeployLog for deploy %s stage=%s",
                self.deployment_id,
                payload.get("stage"),
            )

    def _update_deploy_row(self, payload: dict) -> None:
        """
        Keep Deploy.progress / stage / status_message in sync so the REST
        API and the WebSocket stay consistent.
        """
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
            if message:
                update_fields["status_message"] = message[:500]

            # Soft terminal transitions driven by stage name only when
            # the row is still non-terminal (monitor / task owns hard fails).
            if stage in self._SUCCESS_STAGES and progress == 100:
                update_fields.setdefault("status", DeploymentStatusChoices.SUCCEEDED)
                update_fields.setdefault("completed_at", timezone.now())
            elif level == "error" and stage in self._FAILURE_STAGES:
                # Do not force FAILED here — Orchestrator / tasks already do.
                # Only enrich error_message when empty.
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
        Push to the Channels group that DeploymentConsumer joined.

        Consumer handler name is ``deployment_message`` → channel type
        must be ``deployment.message``.
        """
        try:
            channel_layer = get_channel_layer()
            if channel_layer is None:
                logger.debug(
                    "No channel layer configured; skipping WS broadcast for %s",
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
                "Channel broadcast failed for deploy %s", self.deployment_id
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_deploy(self) -> Deploy:
        if self._deploy_cache is None:
            self._deploy_cache = Deploy.objects.select_related("service").get(
                pk=self.deployment_id
            )
        return self._deploy_cache


# Backward-compatible alias
class DeploymentEventPipeline(DBAndChannelEventSink):
    """Alias kept for older imports of ``deploy.event_pipeline``."""

    pass
