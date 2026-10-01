from __future__ import annotations

import logging
from typing import Any, Optional

from django.utils import timezone

from deploy.models import Deploy, DeploymentStatusChoices
from deploy.event_pipeline import sanitize

from .types import DeploymentEvent

logger = logging.getLogger(__name__)


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
      1. Keep Deploy.progress / stage / status_message in sync synchronously.
      2. Append non-noise lifecycle events to the durable deployment outbox.
      3. Leave DeployLog and WebSocket delivery to the outbox dispatcher.


    Usage::

        sink = DBAndChannelEventSink(deploy.pk)
        sink(DeploymentEvent(stage="image_build", message="…", progress=25))
    """

    def __init__(self, deployment_id):
        self.deployment_id = str(deployment_id)
        self._deploy_cache: Optional[Deploy] = None

    def __call__(self, event: DeploymentEvent | dict) -> None:
        payload = _serialize_event(event)
        stage = payload.get("stage") or ""
        message = payload.get("message") or ""
        level = payload.get("level") or "info"
        noisy = _is_noisy_build_line(stage, message, level)

        # Deploy progress/stage are synchronous control-plane state. Event
        # persistence and delivery are delegated to the durable outbox so
        # DeployLog and WebSocket remain projections rather than authorities.
        self._update_deploy_row(payload, skip_message=noisy and level == "info")

        # Pure Docker build noise is intentionally not journaled. Errors and
        # warnings always enter the durable event stream.
        if noisy and level not in ("error", "warning"):
            return

        try:
            from deploy.event_pipeline import DeploymentEventPipeline as DurableEventPipeline
            deploy = self._get_deploy()
            DurableEventPipeline(deploy).record(
                DeploymentEvent(
                    stage=payload.get("stage") or "",
                    message=payload.get("message") or "",
                    level=payload.get("level") or "info",
                    progress=payload.get("progress"),
                    details=payload.get("details") or {},
                )
            )
        except Exception:
            logger.exception(
                "Failed to persist durable deployment event for deploy %s stage=%s",
                self.deployment_id,
                payload.get("stage"),
            )

    def record(self, event: DeploymentEvent | dict) -> None:
        self(event)

    def _update_deploy_row(self, payload: dict, *, skip_message: bool = False) -> None:
        try:
            progress = payload.get("progress")
            stage = payload.get("stage") or ""
            message = sanitize(payload.get("message") or "")

            update_fields: dict[str, Any] = {}
            if progress is not None:
                try:
                    update_fields["progress"] = max(0, min(100, int(progress)))
                except (TypeError, ValueError):
                    pass
            if stage:
                update_fields["stage"] = str(stage)[:64]
            if message and not skip_message:
                update_fields["status_message"] = str(message)[:500]

            if not update_fields:
                return

            # This projection never mutates Deploy.status and never persists
            # secret-bearing event text into lifecycle state.
            Deploy.objects.filter(pk=self.deployment_id).exclude(
                status__in=(
                    DeploymentStatusChoices.SUCCEEDED,
                    DeploymentStatusChoices.FAILED,
                    DeploymentStatusChoices.CANCELLED,
                    DeploymentStatusChoices.ROLLED_BACK,
                )
            ).update(**update_fields)
        except Exception:
            logger.exception(
                "Failed to update Deploy progress for %s",
                self.deployment_id,
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
