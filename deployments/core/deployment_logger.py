import logging
from typing import Optional

from .types import DeploymentEvent, EventSink
from .exceptions import DeploymentCancelled


class DeploymentLogger:
    """
    Emit structured deployment events to Python logging and an optional sink.

    The sink (typically DBAndChannelEventSink) is responsible for:
      - DeployLog rows
      - Deploy progress/stage updates
      - WebSocket broadcast to the browser

    Sink failures never abort the pipeline (except DeploymentCancelled).
    """

    def __init__(
        self,
        *,
        deployment_id: Optional[str] = None,
        sink: Optional[EventSink] = None,
    ):
        self.deployment_id = str(deployment_id) if deployment_id is not None else None
        self.sink = sink
        self.logger = logging.getLogger("deployments.lifecycle")
        self._sink_error_count = 0

    def emit(
        self,
        stage: str,
        message: str,
        *,
        level: str = "info",
        progress=None,
        details=None,
    ):
        event = DeploymentEvent(
            stage=stage,
            message=message,
            level=level,
            progress=progress,
            details=details or {},
        )

        log_method = getattr(self.logger, level, self.logger.info)

        # CRITICAL: the celery log formatter only renders ``%(message)s``.
        # ``extra`` fields (including ``deployment_details``) are silently
        # dropped by default.  To make diagnostics actually visible in the
        # worker log, we append high-signal fields from ``details`` to the
        # message text on a continuation line.  This is what makes the
        # difference between "Failed to create container 'X'." and
        # "Failed to create container 'X'. Docker APIError: <reason>".
        rendered_message = self._render_log_message(stage, message, event.details)

        log_method(
            "%s",
            rendered_message,
            extra={
                "deployment_id": self.deployment_id,
                "deployment_stage": stage,
                "deployment_progress": progress,
                "deployment_details": event.details,
            },
        )

        if self.sink is not None:
            try:
                self.sink(event)
            except DeploymentCancelled:
                raise
            except Exception:
                self._sink_error_count += 1
                # Log first failures loudly; avoid flooding if sink is permanently broken
                if self._sink_error_count <= 3:
                    self.logger.exception(
                        "Deployment event sink failed (count=%s) deploy=%s stage=%s",
                        self._sink_error_count,
                        self.deployment_id,
                        stage,
                    )
                elif self._sink_error_count == 4:
                    self.logger.error(
                        "Deployment event sink keeps failing; further sink "
                        "errors will be sampled at 1/100 for deploy=%s",
                        self.deployment_id,
                    )
                elif self._sink_error_count % 100 == 0:
                    # Legacy code suppressed ALL errors after count=4,
                    # making a permanently broken sink invisible.  We
                    # now log a summary every 100 errors so operators
                    # always have visibility.
                    self.logger.error(
                        "Deployment event sink has failed %s times for "
                        "deploy=%s (last stage=%s). Sink is likely "
                        "permanently broken — investigate channel layer "
                        "and log database.",
                        self._sink_error_count,
                        self.deployment_id,
                        stage,
                    )

        return event

    @staticmethod
    def _render_log_message(stage: str, message: str, details: dict) -> str:
        """
        Build the celery-visible log message.

        Format: ``stage | message`` optionally followed by a continuation
        line with the most diagnostic detail fields.

        We surface only the fields most useful for debugging the actual
        Docker / deployment failure (``error``, ``error_type``,
        ``status_code``, ``stage``, ``last_stage``, ``image_present``,
        ``networks``, ``volumes``).  Other details stay in the structured
        ``extra`` for sinks / dashboards.
        """
        base = f"{stage} | {message}"
        if not details:
            return base

        # Always include the underlying engine error if present — this
        # is the single most important field for diagnosing create / start
        # / network / volume failures, and the legacy code dropped it.
        diagnostic_keys = (
            "error",
            "error_type",
            "status_code",
            "last_stage",
            "image_present",
            "exit_code",
            "container",
            "image",
            "network",
            "volume",
            "networks",
            "volumes",
            "previous_image_ref",
            "rollback_performed",
            "rollback_failed",
        )
        parts = []
        for key in diagnostic_keys:
            if key not in details:
                continue
            value = details[key]
            if value is None or value == "" or value == []:
                continue
            if isinstance(value, (list, dict)):
                value = repr(value)
            else:
                value = str(value)
            if len(value) > 400:
                value = value[:400] + "...(truncated)"
            parts.append(f"{key}={value}")

        if not parts:
            return base
        return f"{base} | {' '.join(parts)}"

    def debug(self, stage: str, message: str, *, progress=None, details=None):
        return self.emit(
            stage, message, level="debug", progress=progress, details=details
        )

    def info(self, stage: str, message: str, *, progress=None, details=None):
        return self.emit(
            stage, message, level="info", progress=progress, details=details
        )

    def warning(self, stage: str, message: str, *, progress=None, details=None):
        return self.emit(
            stage, message, level="warning", progress=progress, details=details
        )

    def error(self, stage: str, message: str, *, progress=None, details=None):
        return self.emit(
            stage, message, level="error", progress=progress, details=details
        )
