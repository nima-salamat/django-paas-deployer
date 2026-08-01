"""
deployments/celery/monitoring/actions.py
-----------------------------------------
Pure state-writer helpers used by the reconciliation rules.

Every function that changes Service or Deploy status lives here so the
monitor rules stay readable and the side-effects stay testable.

Rules for all writers
---------------------
* Always run inside transaction.atomic().
* select_for_update() the row(s) being changed, then re-read current status
  before writing — skip if another worker already transitioned the row.
* Use update_fields to avoid accidental over-writes of unrelated columns.
* Call create_deploy_log() for every automatic transition so the event log
  remains complete for the user.
* Clear service.task_id when reaching a terminal state
  (running / stopped / failed).
* Set deploy.completed_at when the deploy reaches a terminal state.
"""

import logging

from django.db import transaction
from django.utils import timezone

from core.global_settings.config import SERVICE_STATUS_CHOICES, MAX_DEPLOY_TIME_MINUTE
from deploy.models import Deploy, DeployLog, DeploymentStatusChoices, RollbackStatusChoices
from services.models import Service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _create_deploy_log(
    deploy: Deploy,
    stage: str,
    message: str,
    *,
    level: str = "info",
    event_type: str = "deployment.monitor",
    progress: int | None = None,
    details: dict | None = None,
) -> None:
    """
    Write a DeployLog entry.  Failures are swallowed so a log-write error
    never aborts a state transition that already succeeded.
    """
    try:
        DeployLog.objects.create(
            deploy_id=deploy.pk,       
            service_id=deploy.service.pk,  
            stage=stage,
            event_type=event_type,
            level=level,
            message=message,
            progress=progress,
            details=details or {},
        )
    except Exception:
        logger.exception(
            "Failed to write DeployLog for deploy %s stage=%s", deploy.pk, stage
        )
# ---------------------------------------------------------------------------
# Service-level writers
# ---------------------------------------------------------------------------

@transaction.atomic
def mark_service_running(service: Service, deploy: Deploy | None = None) -> bool:
    """
    Transition a service to RUNNING (container confirmed up after deploy).

    Returns True if the transition was applied, False if skipped (already
    in a terminal state or transitioned by another worker).
    """
    locked = (
        Service.objects
        .select_for_update()
        .filter(pk=service.pk)
        .first()
    )
    if locked is None:
        return False

    # Only advance from transient states; do not overwrite a manual stop.
    allowed = (
        SERVICE_STATUS_CHOICES.QUEUED,
        SERVICE_STATUS_CHOICES.DEPLOYING,
        SERVICE_STATUS_CHOICES.SUCCEEDED,   # legacy rows
        SERVICE_STATUS_CHOICES.RUNNING,     # idempotent
    )
    if locked.status not in allowed:
        return False

    if locked.status == SERVICE_STATUS_CHOICES.RUNNING:
        # Already running — idempotent, nothing to write.
        return True

    now = timezone.now()
    Service.objects.filter(pk=service.pk).update(
        status=SERVICE_STATUS_CHOICES.RUNNING,
        deployed_at=now,
        deploy_started=None,
        task_id=None,
    )

    logger.info("Service %s → running", service.pk)

    if deploy is not None:
        _create_deploy_log(
            deploy,
            stage="monitor",
            message="Service is running. Container confirmed up.",
            level="info",
            event_type="deployment.monitor",
            details={"previous_status": locked.status, "new_status": "running"},
        )
    return True


@transaction.atomic
def mark_service_stopped(service: Service, deploy: Deploy | None = None) -> bool:
    """
    Transition a service to STOPPED (stop completed or container gone after
    user-initiated stop).

    Returns True if applied.
    """
    locked = (
        Service.objects
        .select_for_update()
        .filter(pk=service.pk)
        .first()
    )
    if locked is None:
        return False

    allowed = (
        SERVICE_STATUS_CHOICES.STOPPING,
        SERVICE_STATUS_CHOICES.STOPPED,   # idempotent
    )
    if locked.status not in allowed:
        return False

    if locked.status == SERVICE_STATUS_CHOICES.STOPPED:
        return True  # idempotent

    Service.objects.filter(pk=service.pk).update(
        status=SERVICE_STATUS_CHOICES.STOPPED,
        task_id=None,
    )

    logger.info("Service %s → stopped", service.pk)

    if deploy is not None:
        _create_deploy_log(
            deploy,
            stage="monitor",
            message="Service stopped. Container is no longer running.",
            level="info",
            event_type="deployment.monitor",
            details={"previous_status": locked.status, "new_status": "stopped"},
        )
    return True


@transaction.atomic
def mark_service_failed(
    service: Service,
    message: str,
    deploy: Deploy | None = None,
    *,
    details: dict | None = None,
) -> bool:
    """
    Transition a service to FAILED.

    Returns True if applied.
    """
    locked = (
        Service.objects
        .select_for_update()
        .filter(pk=service.pk)
        .first()
    )
    if locked is None:
        return False

    # Never overwrite a user-initiated stop that completed cleanly.
    if locked.status == SERVICE_STATUS_CHOICES.STOPPED:
        return False

    Service.objects.filter(pk=service.pk).update(
        status=SERVICE_STATUS_CHOICES.FAILED,
        deploy_started=None,
        task_id=None,
    )

    logger.warning("Service %s → failed: %s", service.pk, message)

    if deploy is not None:
        _create_deploy_log(
            deploy,
            stage="monitor",
            message=message,
            level="error",
            event_type="deployment.monitor",
            details={
                "previous_status": locked.status,
                "new_status": "failed",
                **(details or {}),
            },
        )
    return True


# ---------------------------------------------------------------------------
# Deploy-level writers
# ---------------------------------------------------------------------------

@transaction.atomic
def mark_deploy_failed(
    deploy: Deploy,
    message: str,
    stage: str,
    *,
    details: dict | None = None,
) -> bool:
    """
    Mark a Deploy as FAILED, set completed_at, write a DeployLog.

    Also fails the associated Service unless it is already in a terminal
    (stopped / failed) state.

    Returns True if applied.
    """
    locked = (
        Deploy.objects
        .select_related("service")
        .select_for_update()
        .filter(pk=deploy.pk)
        .first()
    )
    if locked is None:
        return False

    # Skip if already terminal.
    terminal = (
        DeploymentStatusChoices.SUCCEEDED,
        DeploymentStatusChoices.FAILED,
        DeploymentStatusChoices.ROLLED_BACK,
        DeploymentStatusChoices.CANCELLED,
    )
    if locked.status in terminal:
        return False

    now = timezone.now()
    Deploy.objects.filter(pk=deploy.pk).update(
        status=DeploymentStatusChoices.FAILED,
        stage=stage,
        error_message=message,
        status_message="Deployment failed.",
        completed_at=now,
    )

    logger.warning("Deploy %s → failed [%s]: %s", deploy.pk, stage, message)

    _create_deploy_log(
        locked,
        stage=stage,
        message=message,
        level="error",
        event_type="deployment.monitor",
        details={
            "deploy_status_before": locked.status,
            **(details or {}),
        },
    )

    # Cascade to service
    service = locked.service
    if service and service.status not in (
        SERVICE_STATUS_CHOICES.STOPPED,
        SERVICE_STATUS_CHOICES.FAILED,
    ):
        Service.objects.filter(pk=service.pk).update(
            status=SERVICE_STATUS_CHOICES.FAILED,
            deploy_started=None,
            task_id=None,
        )
        logger.warning("Service %s → failed (deploy failed)", service.pk)

    return True


@transaction.atomic
def mark_deploy_timeout(
    deploy: Deploy,
    *,
    container_exists: bool,
    container_running: bool,
) -> bool:
    """
    Handle a deploy that exceeded the timeout threshold.

    Marks both the Deploy and its Service as failed and writes an
    event log with timeout details.

    Returns True if applied.
    """
    locked = (
        Deploy.objects
        .select_related("service")
        .select_for_update()
        .filter(pk=deploy.pk)
        .first()
    )
    if locked is None:
        return False

    terminal = (
        DeploymentStatusChoices.SUCCEEDED,
        DeploymentStatusChoices.FAILED,
        DeploymentStatusChoices.ROLLED_BACK,
        DeploymentStatusChoices.CANCELLED,
    )
    if locked.status in terminal:
        return False

    message = (
        f"Deployment exceeded the maximum allowed time "
        f"of {MAX_DEPLOY_TIME_MINUTE} minutes."
    )
    now = timezone.now()

    Deploy.objects.filter(pk=deploy.pk).update(
        status=DeploymentStatusChoices.FAILED,
        stage="timeout",
        error_message=message,
        status_message="Deployment timed out.",
        progress=min(locked.progress, 99),
        completed_at=now,
    )

    logger.warning("Deploy %s → timed out", deploy.pk)

    # Re-fetch for log creation so the FK references are correct
    refreshed = Deploy.objects.select_related("service").get(pk=deploy.pk)
    _create_deploy_log(
        refreshed,
        stage="timeout",
        message=message,
        level="error",
        event_type="deployment.timeout",
        details={
            "container_exists": container_exists,
            "container_running": container_running,
            "max_deploy_time_minutes": MAX_DEPLOY_TIME_MINUTE,
        },
    )

    # Cascade to service
    service = locked.service
    if service and service.status not in (
        SERVICE_STATUS_CHOICES.STOPPED,
        SERVICE_STATUS_CHOICES.FAILED,
    ):
        Service.objects.filter(pk=service.pk).update(
            status=SERVICE_STATUS_CHOICES.FAILED,
            deploy_started=None,
            task_id=None,
        )
        logger.warning("Service %s → failed (deploy timeout)", service.pk)

    return True


@transaction.atomic
def mark_rollback_complete(deploy: Deploy) -> bool:
    """
    Mark rollback as succeeded, service as running.

    Returns True if applied.
    """
    locked = (
        Deploy.objects
        .select_related("service")
        .select_for_update()
        .filter(pk=deploy.pk)
        .first()
    )
    if locked is None or locked.status != DeploymentStatusChoices.ROLLING_BACK:
        return False

    Deploy.objects.filter(pk=deploy.pk).update(
        rollback_status=RollbackStatusChoices.SUCCEEDED,
        status=DeploymentStatusChoices.ROLLED_BACK,
        stage="rollback_completed",
        progress=100,
        status_message="Rollback completed successfully.",
        completed_at=timezone.now(),
    )

    _create_deploy_log(
        locked,
        stage="rollback_completed",
        message="Rollback completed successfully.",
        level="info",
        event_type="deployment.rollback",
        progress=100,
    )

    service = locked.service
    if service:
        Service.objects.filter(pk=service.pk).update(
            status=SERVICE_STATUS_CHOICES.RUNNING,
            deploy_started=None,
            task_id=None,
        )
        logger.info("Service %s → running (rollback complete)", service.pk)

    return True


@transaction.atomic
def mark_rollback_failed(deploy: Deploy) -> bool:
    """
    Mark rollback as failed, service as failed.

    Returns True if applied.
    """
    locked = (
        Deploy.objects
        .select_related("service")
        .select_for_update()
        .filter(pk=deploy.pk)
        .first()
    )
    if locked is None or locked.status != DeploymentStatusChoices.ROLLING_BACK:
        return False

    message = "Rollback failed because the deployment container does not exist."

    Deploy.objects.filter(pk=deploy.pk).update(
        rollback_status=RollbackStatusChoices.FAILED,
        status=DeploymentStatusChoices.FAILED,
        stage="rollback_failed",
        error_message=message,
        completed_at=timezone.now(),
    )

    _create_deploy_log(
        locked,
        stage="rollback_failed",
        message=message,
        level="error",
        event_type="deployment.rollback",
    )

    service = locked.service
    if service and service.status not in (
        SERVICE_STATUS_CHOICES.STOPPED,
        SERVICE_STATUS_CHOICES.FAILED,
    ):
        Service.objects.filter(pk=service.pk).update(
            status=SERVICE_STATUS_CHOICES.FAILED,
            deploy_started=None,
            task_id=None,
        )
        logger.warning("Service %s → failed (rollback failed)", service.pk)

    return True
