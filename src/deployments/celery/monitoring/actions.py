from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.global_settings.config import SERVICE_STATUS_CHOICES
from deploy.models import Deploy, DeployLog, DeploymentStatusChoices, RollbackStatusChoices
from services.models import Service
from deployments.core.state.manager import StateManager

logger = logging.getLogger(__name__)


def _log_db_alias() -> str:
    return getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"


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
    Write a DeployLog entry (cross-DB safe) and best-effort broadcast
    to the WebSocket group.
    """
    try:
        DeployLog.objects.using(_log_db_alias()).create(
            deploy_id=deploy.pk,
            service_id=getattr(deploy, "service_id", None)
            or (deploy.service.pk if getattr(deploy, "service", None) else None),
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

    # Live push to connected browsers
    try:
        try:
            from deployments.core.sink import DBAndChannelEventSink
        except ImportError:
            from deploy.sink import DBAndChannelEventSink
        from deployments.core.types import DeploymentEvent

        sink = DBAndChannelEventSink(deploy.pk)
        sink(
            DeploymentEvent(
                stage=stage,
                message=message,
                level=level,
                progress=progress,
                details=details or {},
            )
        )
    except Exception:
        logger.debug(
            "Monitor WS broadcast skipped for deploy %s", deploy.pk, exc_info=True
        )


# ---------------------------------------------------------------------------
# Service-level writers
# ---------------------------------------------------------------------------

@transaction.atomic
def mark_service_running(service: Service, deploy: Deploy | None = None) -> bool:
    locked = (
        Service.objects
        .select_for_update()
        .filter(pk=service.pk)
        .first()
    )
    if locked is None:
        return False

    allowed = (
        SERVICE_STATUS_CHOICES.QUEUED,
        SERVICE_STATUS_CHOICES.DEPLOYING,
        SERVICE_STATUS_CHOICES.SUCCEEDED,
        SERVICE_STATUS_CHOICES.RUNNING,
    )
    if locked.status not in allowed:
        return False

    if locked.status == SERVICE_STATUS_CHOICES.RUNNING:
        return True

    now = timezone.now()
    StateManager.transition_service(
        service.pk, SERVICE_STATUS_CHOICES.RUNNING,
        update_fields={"deployed_at": now, "deploy_started": None, "task_id": None},
    )

    logger.info("Service %s → running", service.pk)

    if deploy is not None:
        _create_deploy_log(
            deploy,
            stage="monitor",
            message="Service is running. Container confirmed up.",
            level="info",
            event_type="deployment.monitor",
            progress=100,
            details={"previous_status": locked.status, "new_status": "running"},
        )
    return True


@transaction.atomic
def mark_service_stopped(service: Service, deploy: Deploy | None = None) -> bool:
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
        SERVICE_STATUS_CHOICES.STOPPED,
    )
    if locked.status not in allowed:
        return False

    if locked.status == SERVICE_STATUS_CHOICES.STOPPED:
        return True

    StateManager.transition_service(
        service.pk, SERVICE_STATUS_CHOICES.STOPPED,
        update_fields={"task_id": None},
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
    locked = (
        Service.objects
        .select_for_update()
        .filter(pk=service.pk)
        .first()
    )
    if locked is None:
        return False

    if locked.status == SERVICE_STATUS_CHOICES.STOPPED:
        return False

    StateManager.transition_service(
        service.pk, SERVICE_STATUS_CHOICES.FAILED,
        update_fields={"deploy_started": None, "task_id": None},
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

    now = timezone.now()
    StateManager.transition_deploy(
        deploy.pk, DeploymentStatusChoices.FAILED,
        update_fields={
            "stage": stage, "error_message": message,
            "status_message": "Deployment failed.",
        },
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

    service = locked.service
    if service and service.status not in (
        SERVICE_STATUS_CHOICES.STOPPED,
        SERVICE_STATUS_CHOICES.FAILED,
    ):
        StateManager.transition_service(
            service.pk, SERVICE_STATUS_CHOICES.FAILED,
            update_fields={"deploy_started": None, "task_id": None},
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
    """Request cancellation of a timed-out deployment; cleanup is worker-owned."""
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
    if locked.status in terminal or locked.cancel_requested:
        return False

    try:
        from core.settings_service import deploy_timeout_minutes
        max_minutes = deploy_timeout_minutes()
    except Exception:
        max_minutes = 10
    message = f"Deployment exceeded the maximum allowed time of {max_minutes} minutes."

    Deploy.objects.filter(pk=deploy.pk).update(
        cancel_requested=True,
        stage="timeout_requested",
        status_message="Deployment timed out; stopping active deployment work.",
        error_message=message,
        progress=min(locked.progress or 0, 99),
    )

    logger.warning("Deploy %s → timeout cancellation requested", deploy.pk)

    refreshed = Deploy.objects.select_related("service").get(pk=deploy.pk)
    _create_deploy_log(
        refreshed,
        stage="timeout",
        message=message,
        level="error",
        event_type="deployment.timeout_requested",
        details={
            "container_exists": container_exists,
            "container_running": container_running,
            "max_deploy_time_minutes": max_minutes,
        },
    )

    # The worker owns cleanup. It will observe ``cancel_requested``, close an
    # active Docker build stream, stop/remove a replacement container, restore
    # the previous release when necessary, and commit one terminal event.
    # Avoid hard-revoking it here because SIGTERM can interrupt cleanup midway.
    return True


@transaction.atomic
def mark_rollback_complete(deploy: Deploy) -> bool:
    locked = (
        Deploy.objects
        .select_related("service")
        .select_for_update()
        .filter(pk=deploy.pk)
        .first()
    )
    if locked is None or locked.status != DeploymentStatusChoices.ROLLING_BACK:
        return False

    StateManager.transition_deploy(
        deploy.pk, DeploymentStatusChoices.ROLLED_BACK,
        update_fields={
            "rollback_status": RollbackStatusChoices.SUCCEEDED,
            "stage": "rollback_completed",
            "progress": 100,
            "status_message": "Rollback completed successfully.",
        },
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
        StateManager.transition_service(
            service.pk, SERVICE_STATUS_CHOICES.RUNNING,
            update_fields={"deploy_started": None, "task_id": None},
        )
        logger.info("Service %s → running (rollback complete)", service.pk)

    return True


@transaction.atomic
def mark_rollback_failed(deploy: Deploy) -> bool:
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

    StateManager.transition_deploy(
        deploy.pk, DeploymentStatusChoices.FAILED,
        update_fields={
            "rollback_status": RollbackStatusChoices.FAILED,
            "stage": "rollback_failed",
            "error_message": message,
        },
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
        StateManager.transition_service(
            service.pk, SERVICE_STATUS_CHOICES.FAILED,
            update_fields={"deploy_started": None, "task_id": None},
        )
        logger.warning("Service %s → failed (rollback failed)", service.pk)

    return True
