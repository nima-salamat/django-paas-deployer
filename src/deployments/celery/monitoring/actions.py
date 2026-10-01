from __future__ import annotations

import logging
import uuid
from typing import Optional

from django.db import transaction
from django.utils import timezone

from core.global_settings.config import SERVICE_STATUS_CHOICES
from deploy.models import Deploy, DeploymentStatusChoices, RollbackStatusChoices
from services.models import Service
from deployments.core.state.manager import StateManager

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
    """Persist a monitor event through the durable deployment outbox."""
    try:
        from deployments.core.sink import DBAndChannelEventSink
        from deployments.core.types import DeploymentEvent

        DBAndChannelEventSink(deploy.pk)(
            DeploymentEvent(
                stage=stage,
                message=message,
                level=level,
                progress=progress,
                details={
                    **(details or {}),
                    "event_type": event_type,
                },
            )
        )
    except Exception:
        logger.exception(
            "Failed to persist durable monitor event for deploy %s stage=%s",
            deploy.pk,
            stage,
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
    StateManager.transition_deploy_system_terminal(
        deploy.pk,
        DeploymentStatusChoices.FAILED,
        update_fields={
            "stage": stage,
            "error_message": message,
            "status_message": "Deployment failed.",
        },
        event_payload={
            "event_id": str(uuid.uuid4()),
            "trace_id": str(deploy.pk),
            "deployment_id": str(deploy.pk),
            "service_id": str(locked.service_id),
            "revision_id": str(getattr(locked, "revision_id", "") or ""),
            "task_id": "system",
            "event_type": "deployment.deployment_failed.error",
            "stage": "deployment_failed",
            "level": "error",
            "message": message,
            "progress": 100,
            "details": {
                "failure_stage": stage,
                "deploy_status_before": locked.status,
                **(details or {}),
            },
        },
    )

    logger.warning("Deploy %s → failed [%s]: %s", deploy.pk, stage, message)

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
        from core.settings_service import (
            base_image_build_timeout_minutes,
            deploy_timeout_minutes,
        )
        phase = str(locked.stage or "").strip().lower()
        if phase == "base_image":
            max_minutes = base_image_build_timeout_minutes()
            message = (
                "The required base runtime image could not become ready within "
                f"the {max_minutes}-minute base-image build/wait limit."
            )
        else:
            max_minutes = deploy_timeout_minutes()
            message = (
                "The deployment exceeded the "
                f"{max_minutes}-minute application deployment limit after the "
                "required base runtime image became ready."
            )
    except Exception:
        phase = str(locked.stage or "").strip().lower()
        max_minutes = 10
        message = (
            "The required base runtime image could not become ready within the "
            "10-minute base-image build/wait limit."
            if phase == "base_image"
            else "The deployment exceeded the 10-minute application deployment limit."
        )

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
            "timeout_phase": "base_image" if phase == "base_image" else "application",
            "base_image_build_timeout_minutes": (
                base_image_build_timeout_minutes() if phase == "base_image" else None
            ),
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

    StateManager.transition_deploy_system_terminal(
        deploy.pk,
        DeploymentStatusChoices.ROLLED_BACK,
        update_fields={
            "rollback_status": RollbackStatusChoices.SUCCEEDED,
            "stage": "rollback_completed",
            "progress": 100,
            "status_message": "Rollback completed successfully.",
        },
        event_payload={
            "event_id": str(__import__("uuid").uuid4()),
            "trace_id": str(deploy.pk),
            "deployment_id": str(deploy.pk),
            "service_id": str(locked.service_id),
            "revision_id": str(getattr(locked, "revision_id", "") or ""),
            "task_id": "system",
            "event_type": "deployment.rollback_completed.info",
            "stage": "rollback_completed",
            "level": "info",
            "message": "Rollback completed successfully.",
            "progress": 100,
            "details": {"deploy_status_before": locked.status},
        },
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

    StateManager.transition_deploy_system_terminal(
        deploy.pk,
        DeploymentStatusChoices.FAILED,
        update_fields={
            "rollback_status": RollbackStatusChoices.FAILED,
            "stage": "rollback_failed",
            "error_message": message,
        },
        event_payload={
            "event_id": str(__import__("uuid").uuid4()),
            "trace_id": str(deploy.pk),
            "deployment_id": str(deploy.pk),
            "service_id": str(locked.service_id),
            "revision_id": str(getattr(locked, "revision_id", "") or ""),
            "task_id": "system",
            "event_type": "deployment.rollback_failed.error",
            "stage": "rollback_failed",
            "level": "error",
            "message": message,
            "progress": 100,
            "details": {"deploy_status_before": locked.status},
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
        logger.warning("Service %s → failed (rollback failed)", service.pk)

    return True
