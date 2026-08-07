from django.db import transaction
from django.utils import timezone
import logging

from .event_pipeline import DeploymentEventPipeline
from .models import Deploy, DeploymentStatusChoices, RollbackStatusChoices
from deployments.core.exceptions import DeploymentCancelled
from deployments.core.types import DeploymentEvent

logger = logging.getLogger(__name__)

RESOURCE_STATUS_FIELDS = {
    "image_build": ("image_status", "building"),
    "network_creation": ("network_status", "creating"),
    "volume_creation": ("volume_status", "creating"),
    "container_creation": ("container_status", "creating"),
    "container_replacement": ("container_status", "replacing"),
    "container_startup": ("container_status", "starting"),
    "health_check": ("health_status", "checking"),
}

STAGE_STATUS_MESSAGES = {
    "deployment_started": "Deployment started.",
    "validation": "Validating deployment.",
    "prepare_resources": "Preparing deployment resources.",
    "platform_detection": "Detecting project platform.",
    "entrypoint_detection": "Detecting application entrypoint.",
    "image_build": "Building image.",
    "network_creation": "Preparing networks.",
    "volume_creation": "Preparing volumes.",
    "state_snapshot": "Capturing previous container state.",
    "container_creation": "Creating container.",
    "container_replacement": "Replacing existing container.",
    "container_startup": "Starting container.",
    "health_check": "Checking health.",
    "rollback": "Rolling back deployment.",
    "cleanup": "Cleaning up resources.",
    "deployment_completed": "Deployment completed.",
    "deployment_failed": "Deployment failed.",
    "cancelled": "Deployment cancelled.",
    "celery_setup": "Configuring Celery workers.",
    "dockerfile_generation": "Generating Dockerfile.",
}


class DjangoDeploymentState:
    """
    Tracks one Deploy row through start → live events → finish / exception.

    ``event_sink`` is a bound method used as the EventSink callable by
    DeploymentOrchestrator / DeployFacade / DeploymentLogger.
    """

    def __init__(self, deploy: Deploy):
        if deploy is None:
            raise ValueError("DjangoDeploymentState requires a Deploy instance")
        self.deploy = deploy
        self.events = DeploymentEventPipeline(deploy)
        self._finished = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self._finished = False
        self._update_deploy(
            status=DeploymentStatusChoices.RUNNING,
            stage="deployment_started",
            progress=0,
            status_message="Deployment started.",
            error_message="",
            rollback_status=RollbackStatusChoices.NOT_REQUIRED,
            health_status="pending",
            container_status="pending",
            image_status="pending",
            volume_status="pending",
            network_status="pending",
            started_at=timezone.now(),
            completed_at=None,
            cancel_requested=False,
        )
        try:
            self.events.record(
                DeploymentEvent(
                    stage="deployment_started",
                    message="Deployment started.",
                    level="info",
                    progress=0,
                )
            )
        except DeploymentCancelled:
            raise
        except Exception:
            logger.exception(
                "Failed to record deployment_started for deploy %s",
                self.deploy.pk,
            )

    def event_sink(self, event: DeploymentEvent):
        """
        Callable EventSink used by Orchestrator / DeploymentLogger.

        Raises DeploymentCancelled when the user has requested cancel so the
        orchestrator can abort cleanly.
        """
        # Fresh read for cancel flag (avoid stale in-memory value)
        if Deploy.objects.filter(pk=self.deploy.pk, cancel_requested=True).exists():
            raise DeploymentCancelled("Deployment was cancelled by the user.")

        if self._finished:
            # Ignore late events after finish() already wrote terminal state
            try:
                self.events.record(event)
            except Exception:
                logger.debug(
                    "Late event after finish ignored/failed deploy=%s stage=%s",
                    self.deploy.pk,
                    getattr(event, "stage", None),
                    exc_info=True,
                )
            return

        stage = (event.stage or "").strip()
        message = (event.message or "").strip()
        level = (event.level or "info").lower()
        details = event.details or {}

        update = {
            "stage": stage[:64] if stage else self.deploy.stage,
            "status_message": (
                STAGE_STATUS_MESSAGES.get(stage, message) or message
            )[:500],
        }

        if event.progress is not None:
            try:
                new_progress = max(0, min(int(event.progress), 100))
            except (TypeError, ValueError):
                new_progress = None
            if new_progress is not None:
                # Never move progress backwards except on explicit failure/cancel
                current = int(getattr(self.deploy, "progress", 0) or 0)
                if new_progress >= current or level == "error" or stage in (
                    "deployment_failed",
                    "cancelled",
                    "rollback",
                ):
                    update["progress"] = new_progress

        if level == "error" and message:
            update["error_message"] = message[:1000]

        if stage in RESOURCE_STATUS_FIELDS:
            field, value = RESOURCE_STATUS_FIELDS[stage]
            update[field] = self._resource_value(event, value)

        if stage == "deployment_completed":
            update.update(
                {
                    "status": DeploymentStatusChoices.SUCCEEDED,
                    "progress": 100,
                    "completed_at": timezone.now(),
                    "image_status": "built",
                    "network_status": "ready",
                    "volume_status": "ready",
                    "container_status": "running",
                    "health_status": "healthy",
                    "error_message": "",
                }
            )
            self._finished = True

        if stage == "rollback":
            update["rollback_status"] = RollbackStatusChoices.PENDING
            update["status"] = DeploymentStatusChoices.ROLLING_BACK

        if stage in ("deployment_failed", "cancelled"):
            terminal_status = (
                DeploymentStatusChoices.CANCELLED
                if stage == "cancelled"
                else DeploymentStatusChoices.FAILED
            )
            update.update(
                {
                    "status": terminal_status,
                    "progress": 100,
                    "completed_at": timezone.now(),
                }
            )
            if details.get("rollback_performed"):
                update["rollback_status"] = RollbackStatusChoices.SUCCEEDED
            elif getattr(self.deploy, "rollback_status", None) == RollbackStatusChoices.PENDING:
                update["rollback_status"] = RollbackStatusChoices.FAILED
            self._finished = True

        self._update_deploy(**update)

        try:
            self.events.record(event)
        except DeploymentCancelled:
            raise
        except Exception:
            logger.exception(
                "Event pipeline record failed deploy=%s stage=%s",
                self.deploy.pk,
                stage,
            )

    def finish(self, result):
        self._finished = True
        success = bool(getattr(result, "success", False))
        result_status = (getattr(result, "status", None) or "").lower()
        result_stage = getattr(result, "stage", None) or ""
        result_message = getattr(result, "message", None) or ""
        result_error = getattr(result, "error", None) or ""
        rollback_performed = bool(getattr(result, "rollback_performed", False))

        update = {
            "completed_at": timezone.now(),
            "progress": 100,
        }

        if success:
            update.update(
                {
                    "status": DeploymentStatusChoices.SUCCEEDED,
                    "stage": "deployment_completed",
                    "status_message": result_message or "Deployment completed.",
                    "error_message": "",
                    "rollback_status": RollbackStatusChoices.NOT_REQUIRED,
                    "health_status": "healthy",
                    "container_status": "running",
                    "image_status": "built",
                    "volume_status": "ready",
                    "network_status": "ready",
                }
            )
            final_stage = "deployment_completed"
            final_level = "info"
        elif result_status == "cancelled" or result_stage == "cancelled":
            update.update(
                {
                    "status": DeploymentStatusChoices.CANCELLED,
                    "stage": "cancelled",
                    "status_message": result_message or "Deployment cancelled.",
                    "error_message": result_error or result_message or "",
                }
            )
            final_stage = "cancelled"
            final_level = "warning"
        else:
            update.update(
                {
                    "status": DeploymentStatusChoices.FAILED,
                    "stage": (result_stage or "deployment_failed")[:64],
                    "status_message": result_message or "Deployment failed.",
                    "error_message": (result_error or result_message or "")[:1000],
                }
            )
            if rollback_performed:
                update["rollback_status"] = RollbackStatusChoices.SUCCEEDED
            elif getattr(self.deploy, "rollback_status", None) == RollbackStatusChoices.PENDING:
                update["rollback_status"] = RollbackStatusChoices.FAILED
            final_stage = update["stage"]
            final_level = "error"

        self._update_deploy(**update)

        try:
            self.events.record(
                DeploymentEvent(
                    stage=final_stage,
                    message=update.get("status_message") or result_message,
                    level=final_level,
                    progress=100,
                    details={"rollback_performed": rollback_performed},
                )
            )
        except Exception:
            logger.exception(
                "Failed to record finish event for deploy %s", self.deploy.pk
            )

    def record_exception(self, exception: Exception, traceback_text: str):
        stage = getattr(exception, "stage", None) or "deployment_failed"
        message = str(exception) or "Deployment failed."
        recoverable = bool(getattr(exception, "recoverable", False))

        try:
            self._update_deploy(
                stage=str(stage)[:64],
                status_message=message[:500],
                error_message=message[:1000],
            )
        except Exception:
            logger.exception(
                "record_exception deploy update failed for %s", self.deploy.pk
            )

        event = DeploymentEvent(
            stage=str(stage)[:64],
            message=message,
            level="error",
            progress=getattr(self.deploy, "progress", None),
            details={
                "recoverable": recoverable,
                "exception_type": type(exception).__name__,
            },
        )
        try:
            # Support both signatures: with / without exception kwargs
            try:
                self.events.record(
                    event,
                    exception=exception,
                    traceback_text=traceback_text or "",
                )
            except TypeError:
                self.events.record(event)
        except Exception:
            logger.exception(
                "record_exception pipeline failed for deploy %s", self.deploy.pk
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resource_value(self, event, default):
        if event.stage == "health_check" and (event.details or {}).get("container_status"):
            return event.details["container_status"]
        if event.level == "error":
            if event.stage == "image_build":
                return "failed"
            if event.stage in (
                "container_creation",
                "container_startup",
                "container_replacement",
            ):
                return "failed"
            if event.stage == "volume_creation":
                return "failed"
            if event.stage == "network_creation":
                return "failed"
            if event.stage == "health_check":
                return "unhealthy"
        return default

    def _update_deploy(self, **fields):
        if not fields:
            return
        try:
            with transaction.atomic():
                Deploy.objects.filter(pk=self.deploy.pk).update(**fields)
                for key, value in fields.items():
                    setattr(self.deploy, key, value)
        except Exception:
            logger.exception(
                "Deploy row update failed deploy=%s fields=%s",
                self.deploy.pk,
                list(fields.keys()),
            )
            raise
