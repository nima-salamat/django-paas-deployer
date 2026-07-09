import logging
from typing import Optional

from .types import DeploymentEvent, EventSink


class DeploymentLogger:
    """Emit structured deployment events to Python logging and an optional sink."""

    def __init__(self, *, deployment_id: Optional[str] = None, sink: Optional[EventSink] = None):
        self.deployment_id = deployment_id
        self.sink = sink
        self.logger = logging.getLogger("deployments.lifecycle")

    def emit(self, stage: str, message: str, *, level: str = "info", progress=None, details=None):
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

        if self.sink:
            try:
                self.sink(event)
            except Exception:
                self.logger.exception("Deployment event sink failed.")

        return event

    def debug(self, stage: str, message: str, *, progress=None, details=None):
        return self.emit(stage, message, level="debug", progress=progress, details=details)

    def info(self, stage: str, message: str, *, progress=None, details=None):
        return self.emit(stage, message, level="info", progress=progress, details=details)

    def warning(self, stage: str, message: str, *, progress=None, details=None):
        return self.emit(stage, message, level="warning", progress=progress, details=details)

    def error(self, stage: str, message: str, *, progress=None, details=None):
        return self.emit(stage, message, level="error", progress=progress, details=details)
