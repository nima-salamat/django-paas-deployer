from django.db import transaction
from django.utils import timezone
import logging

from .event_pipeline import DeploymentEventPipeline
from .models import Deploy, DeploymentStatusChoices, RollbackStatusChoices
from deployments.core.exceptions import DeploymentCancelled
from deployments.core.types import DeploymentEvent
from deployments.core.state.manager import StateManager

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
    "activation": "Activating the ready deployment.",
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

        with transaction.atomic():
            locked = Deploy.objects.select_for_update().get(pk=self.deploy.pk)
            if locked.cancel_requested or locked.status == DeploymentStatusChoices.CANCELLED:
                StateManager.transition_deploy(
                    locked.pk, DeploymentStatusChoices.CANCELLED,
                    update_fields={
                        "stage": "cancelled",
                        "progress": 100,
                        "status_message": "Deployment cancelled before execution.",
                    },
                )
                self.deploy = locked
                self._finished = True
                emit_cancelled = True
            else:
                StateManager.heartbeat_deploy(
                    locked.pk, task_id=getattr(locked, "execution_task_id", None),
                    stage="deployment_started",
                )
                self.deploy = locked
                self._finished = False
                emit_cancelled = False

        try:
            self.events.record(
                DeploymentEvent(
                    stage="cancelled" if emit_cancelled else "deployment_started",
                    message=(
                        "Deployment cancelled before execution. "
                        if emit_cancelled
                        else "Deployment started."
                    ),
                    level="warning" if emit_cancelled else "info",
                    progress=100 if emit_cancelled else 0,
                )
            )
        except DeploymentCancelled:
            raise
        except Exception:
            logger.exception(
                "Failed to record start/cancel event for deploy %s",
                self.deploy.pk,
            )
        return not emit_cancelled

    def event_sink(self, event: DeploymentEvent):
        """
        Callable EventSink used by Orchestrator / DeploymentLogger.

        Raises DeploymentCancelled when the user has requested cancel so the
        orchestrator can abort cleanly.
        """
        # Fresh read for cancellation and ownership. A stale worker must not
        # publish progress or mutate a deployment that has been re-queued
        # under a newer Celery task.
        current = Deploy.objects.filter(pk=self.deploy.pk).values(
            "cancel_requested", "execution_task_id", "status"
        ).first()
        if current and current.get("cancel_requested"):
            raise DeploymentCancelled("Deployment was cancelled by the user.")
        owner = getattr(self.deploy, "execution_task_id", "") or ""
        if owner and current and current.get("execution_task_id") != owner:
            raise DeploymentCancelled(
                "This deployment execution is no longer the active worker owner.",
                stage="stale_worker",
                code="DEPLOYMENT_STALE_WORKER",
                user_message="This deployment attempt was superseded by another worker.",
                details={"expected_task_id": owner, "actual_task_id": current.get("execution_task_id")},
            )

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

    def finish(self, result, *, exception: Exception | None = None, traceback_text: str = ""):
        self._finished = True
        # Compute the intended terminal outcome from the worker's result, then
        # commit it through the ownership-checked StateManager boundary. A
        # stale worker must never be able to overwrite a newer deployment,
        # and cancellation must win over a late success/failure result.
        current = Deploy.objects.filter(pk=self.deploy.pk).values(
            "status", "cancel_requested", "rollback_status", "progress", "execution_task_id"
        ).first()
        cancelled_by_operator = bool(
            current and (
                current.get("cancel_requested")
                or current.get("status") == DeploymentStatusChoices.CANCELLED
            )
        )
        success = False if cancelled_by_operator else bool(getattr(result, "success", False))
        result_status = (getattr(result, "status", None) or "").lower()
        result_stage = getattr(result, "stage", None) or ""
        result_message = getattr(result, "message", None) or ""
        result_error = getattr(result, "error", None) or ""
        rollback_performed = bool(getattr(result, "rollback_performed", False))
        result_details = getattr(result, "details", {}) or {}

        error_code = getattr(exception, "code", None) or result_details.get("error_code")
        error_category = getattr(exception, "category", None) or result_details.get("error_category")
        error_recoverable = (
            getattr(exception, "recoverable", None)
            if exception is not None
            else result_details.get("recoverable")
        )
        error_user_message = getattr(exception, "user_message", None) or result_details.get("user_message")

        update = {
            "completed_at": timezone.now(),
            "progress": 100,
            "execution_task_id": "",
            "worker_heartbeat_at": timezone.now(),
        }

        if success:
            update.update(
                {
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
            terminal_target = DeploymentStatusChoices.SUCCEEDED
            final_stage = "deployment_completed"
            final_level = "info"
        elif cancelled_by_operator or result_status == "cancelled" or result_stage == "cancelled":
            update.update(
                {
                    "stage": "cancelled",
                    "status_message": (
                        "Deployment cancelled by the user." if cancelled_by_operator
                        else result_message or "Deployment cancelled."
                    ),
                    "error_message": result_error or result_message or "",
                }
            )
            terminal_target = DeploymentStatusChoices.CANCELLED
            final_stage = "cancelled"
            final_level = "warning"
        else:
            update.update(
                {
                    "stage": (result_stage or "deployment_failed")[:64],
                    "status_message": (
                        error_user_message
                        or result_message
                        or "Deployment failed."
                    )[:500],
                    "error_message": (
                        error_user_message
                        or result_error
                        or result_message
                        or ""
                    )[:1000],
                }
            )
            if rollback_performed:
                update["rollback_status"] = RollbackStatusChoices.SUCCEEDED
            elif getattr(self.deploy, "rollback_status", None) == RollbackStatusChoices.PENDING:
                update["rollback_status"] = RollbackStatusChoices.FAILED
            terminal_target = DeploymentStatusChoices.FAILED
            final_stage = update["stage"]
            final_level = "error"

        owner = str((current or {}).get("execution_task_id") or getattr(self.deploy, "execution_task_id", "") or "")
        committed = False
        if owner:
            committed = StateManager.transition_deploy_terminal_if_owned(
                self.deploy.pk,
                terminal_target,
                task_id=owner,
                update_fields=update,
            )
        else:
            try:
                StateManager.transition_deploy(
                    self.deploy.pk,
                    terminal_target,
                    update_fields=update,
                )
                committed = True
            except Exception:
                committed = False

        if not committed:
            logger.info(
                "Ignoring stale/duplicate terminal result for deploy=%s owner=%s",
                self.deploy.pk,
                owner or "<none>",
            )
            # Preserve technical diagnostics for operators, but do not emit a
            # second user-facing terminal event for a stale worker.
            if exception is not None or traceback_text:
                try:
                    self.events.record(
                        DeploymentEvent(
                            stage=(getattr(exception, "stage", None) or result_stage or self.deploy.stage or "deployment")[:64],
                            message=(getattr(exception, "technical_message", None) or str(exception) or result_error or result_message or "Deployment result ignored by ownership check.")[:1000],
                            level="error",
                            progress=100,
                            details={
                                "diagnostic": True,
                                "stale_worker": True,
                                "error_code": error_code,
                                "error_category": error_category,
                                "recoverable": error_recoverable,
                            },
                        ),
                        exception=exception,
                        traceback_text=traceback_text or "",
                        broadcast=False,
                    )
                except Exception:
                    logger.exception("Failed to persist stale-worker diagnostics for deploy %s", self.deploy.pk)
            return

        details = {
            "rollback_performed": rollback_performed,
            "error_code": error_code,
            "error_category": error_category,
            "recoverable": bool(error_recoverable) if error_recoverable is not None else None,
        }
        if result_details.get("technical_message"):
            details["technical_message"] = result_details["technical_message"]
        if error_code:
            details["error_code"] = error_code
        if error_category:
            details["error_category"] = error_category
        if error_recoverable is not None:
            details["recoverable"] = bool(error_recoverable)

        try:
            self.events.record(
                DeploymentEvent(
                    stage=final_stage,
                    message=update.get("status_message") or result_message,
                    level=final_level,
                    progress=100,
                    details=details,
                )
            )
        except Exception:
            logger.exception(
                "Failed to record finish event for deploy %s", self.deploy.pk
            )

        if exception is not None or traceback_text:
            technical_stage = (getattr(exception, "stage", None) or final_stage)[:64]
            technical_message = (
                getattr(exception, "technical_message", None)
                or getattr(exception, "message", None)
                or str(exception)
                or result_error
                or result_message
                or "Deployment failed."
            )
            technical_details = {
                "diagnostic": True,
                "error_code": error_code,
                "error_category": error_category,
                "recoverable": error_recoverable,
            }
            try:
                self.events.record(
                    DeploymentEvent(
                        stage=technical_stage,
                        message=technical_message,
                        level="error",
                        progress=100,
                        details=technical_details,
                    ),
                    exception=exception,
                    traceback_text=traceback_text or "",
                    broadcast=False,
                )
            except Exception:
                logger.exception(
                    "Failed to persist technical deployment diagnostics for deploy %s",
                    self.deploy.pk,
                )

    def record_exception(self, exception: Exception, traceback_text: str):
        """Persist technical diagnostics without emitting a second lifecycle failure event.

        Kept for compatibility with older callers; new failure paths should
        call ``finish(..., exception=..., traceback_text=...)`` so the terminal
        state and user-facing event remain canonical.
        """
        stage = str(getattr(exception, "stage", None) or self.deploy.stage or "deployment_failed")[:64]
        message = (
            getattr(exception, "technical_message", None)
            or str(exception)
            or type(exception).__name__
        )
        details = {
            "diagnostic": True,
            "error_code": getattr(exception, "code", None),
            "error_category": getattr(exception, "category", None),
            "recoverable": bool(getattr(exception, "recoverable", False)),
        }
        try:
            self.events.record(
                DeploymentEvent(
                    stage=stage,
                    message=message[:1000],
                    level="error",
                    progress=getattr(self.deploy, "progress", None),
                    details=details,
                ),
                exception=exception,
                traceback_text=traceback_text or "",
                broadcast=False,
            )
        except Exception:
            logger.exception(
                "Failed to persist deployment diagnostics for deploy %s", self.deploy.pk
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
                filters = {"pk": self.deploy.pk}
                owner = getattr(self.deploy, "execution_task_id", "") or ""
                if owner:
                    filters["execution_task_id"] = owner
                fields.setdefault("worker_heartbeat_at", timezone.now())
                updated = Deploy.objects.filter(**filters).exclude(
                    status__in=(
                        DeploymentStatusChoices.SUCCEEDED,
                        DeploymentStatusChoices.FAILED,
                        DeploymentStatusChoices.CANCELLED,
                        DeploymentStatusChoices.ROLLED_BACK,
                    )
                ).update(**fields)
                if not updated and owner:
                    raise RuntimeError(
                        f"Deployment {self.deploy.pk} is no longer owned by task {owner}."
                    )
                for key, value in fields.items():
                    setattr(self.deploy, key, value)
        except Exception:
            logger.exception(
                "Deploy row update failed deploy=%s fields=%s",
                self.deploy.pk,
                list(fields.keys()),
            )
            raise
