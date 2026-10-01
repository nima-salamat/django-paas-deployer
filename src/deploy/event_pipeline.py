"""Fault-tolerant persistence and delivery for deployment lifecycle events."""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings

from .models import DeploymentEventOutbox, DeployLog


logger = logging.getLogger(__name__)
SENSITIVE_KEY_RE = re.compile(r"(password|secret|token|api[_-]?key|private[_-]?key|authorization)", re.I)
SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(password|secret|token|api[_-]?key|authorization)\s*([:=])\s*([^\s,;]+)"
)


def sanitize(value: Any) -> Any:
    """Remove credentials recursively before events leave the worker process."""
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if SENSITIVE_KEY_RE.search(str(key)) else sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_VALUE_RE.sub(r"\1\2[REDACTED]", value)
    return value


class DeploymentEventPipeline:
    """Persist events to the log DB and publish them without affecting deployment work."""

    def __init__(self, deploy):
        self.deploy = deploy
        self.database = settings.DEPLOYMENT_LOG_DB_ALIAS
        self.channel_layer = get_channel_layer()
        self.group_name = f"deploy_{deploy.pk}"

    def record(
        self,
        event,
        *,
        exception: Exception | None = None,
        traceback_text: str = "",
        broadcast: bool = True,
    ) -> dict:
        timestamp = datetime.now(timezone.utc).isoformat()
        details = sanitize(event.details or {})
        event_type = self._event_type(event)
        payload = {
            "event_id": str(uuid.uuid4()),
            "trace_id": self._trace_id(),
            "deployment_id": str(self.deploy.pk),
            "service_id": str(self.deploy.service_id),
            "revision_id": str(getattr(self.deploy, "revision_id", "") or ""),
            "task_id": str(getattr(self.deploy, "execution_task_id", "") or ""),
            "runtime": str(details.get("runtime") or ""),
            "cluster": str(details.get("cluster") or ""),
            "resource": sanitize(details.get("resource") or {}),
            "timestamp": timestamp,
            "occurred_at": timestamp,
            "level": event.level.upper(),
            "stage": event.stage,
            "event": event_type,
            "event_type": event_type,
            "message": sanitize(event.message),
            "progress": event.progress,
            "details": details,
        }
        if exception:
            payload["exception_type"] = type(exception).__name__
        if traceback_text:
            payload["traceback"] = sanitize(traceback_text)

        if not self._is_terminal_event(event):
            try:
                DeploymentEventOutbox.objects.create(
                    event_id=payload["event_id"],
                    deployment_id=self.deploy.pk,
                    service_id=str(self.deploy.service_id),
                    event_type=event_type,
                    stage=str(event.stage or "unknown")[:64],
                    level=str(event.level or "info").lower()[:16],
                    occurred_at=datetime.fromisoformat(timestamp),
                    payload=payload,
                )
            except Exception:
                logger.exception(
                    "Unable to persist deployment event outbox for %s.",
                    self.deploy.pk,
                )

        try:
            log = DeployLog.objects.using(self.database).create(
                deploy_id=self.deploy.pk,
                service_id=self.deploy.service_id,
                stage=event.stage,
                event_type=payload["event"],
                level=event.level.lower(),
                message=payload["message"],
                progress=event.progress,
                details=details,
                exception_type=payload.get("exception_type", ""),
                traceback=payload.get("traceback", ""),
            )
            payload["id"] = str(log.pk)
            try:
                from .log_retention import trim_after_write
                trim_after_write(self.deploy.service_id)
            except Exception:
                pass
        except Exception:
            logger.exception("Unable to persist deployment event for %s.", self.deploy.pk)

        if broadcast:
            self.publish_payload(payload)
        return payload

    def _trace_id(self) -> str:
        try:
            from opentelemetry import trace
            context = trace.get_current_span().get_span_context()
            if context and context.is_valid:
                return format(context.trace_id, "032x")
        except Exception:
            pass
        return str(self.deploy.pk)

    @staticmethod
    def _is_terminal_event(event) -> bool:
        return str(getattr(event, "stage", "") or "") in {
            "deployment_completed",
            "deployment_failed",
            "cancelled",
            "rollback_completed",
            "rollback_failed",
        }

    def publish_payload(self, payload: dict) -> None:
        try:
            if self.channel_layer:
                async_to_sync(self.channel_layer.group_send)(
                    self.group_name,
                    {"type": "deployment.message", "payload": payload},
                )
        except Exception:
            logger.exception(
                "Unable to publish deployment event for %s.",
                self.deploy.pk,
            )

    @staticmethod
    def _event_type(event) -> str:
        if event.stage == "image_build" and event.level in {"debug", "info"}:
            return "image.build.output"
        return f"deployment.{event.stage}.{event.level}"
