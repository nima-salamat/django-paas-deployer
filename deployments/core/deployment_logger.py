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
        log_method(
            "%s | %s",
            stage,
            message,
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
                        "errors will be suppressed for deploy=%s",
                        self.deployment_id,
                    )

        return event

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
