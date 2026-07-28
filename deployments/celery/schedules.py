from datetime import timedelta
import logging

from celery import shared_task
from celery.result import AsyncResult
from django.db import transaction
from django.utils import timezone

from core.global_settings.config import MAX_DEPLOY_TIME_MINUTE
from deployments.core.manager.container_manager import Container
from deploy.models import (
    Deploy,
    DeployLog,
    DeploymentStatusChoices,
    RollbackStatusChoices,
)
from services.models import Service

logger = logging.getLogger(__name__)


def create_deploy_log(
    deploy,
    stage,
    message,
    *,
    level="info",
    event_type="deployment.monitor",
    progress=None,
    details=None,
    exception_type="",
    traceback="",
):
    """
    Create a deployment event log.

    DeployLog is stored separately from the main deployment database,
    so no cross-database FK constraint is created.
    """
    return DeployLog.objects.create(
        deploy=deploy,
        service=deploy.service,
        stage=stage,
        event_type=event_type,
        level=level,
        message=message,
        progress=progress,
        details=details,
        exception_type=exception_type,
        traceback=traceback,
    )


@shared_task
def monitor_services():
    """
    Monitor active deployments and update their status based on
    the Docker container state and deployment task state.
    """

    active_statuses = [
        DeploymentStatusChoices.PENDING,
        DeploymentStatusChoices.RUNNING,
        DeploymentStatusChoices.ROLLING_BACK,
    ]

    deployments = (
        Deploy.objects
        .select_related("service")
        .filter(status__in=active_statuses)
    )

    for deployment in deployments:
        try:
            monitor_deployment(deployment)

        except Exception:
            logger.exception(
                "Monitor error for deployment %s",
                deployment.id,
            )


def monitor_deployment(deployment):
    """
    Monitor a single deployment.
    """

    with transaction.atomic():
        deploy = (
            Deploy.objects
            .select_for_update()
            .select_related("service")
            .get(pk=deployment.pk)
        )

        service = deploy.service

        container = Container(
            service.get_docker_service_name()
        )

        exists = container.exists()
        is_running = container.is_running() if exists else False

        now = timezone.now()

        # ---------------------------------------------------------
        # 1. Deployment timeout
        # ---------------------------------------------------------

        if (
            deploy.status in (
                DeploymentStatusChoices.PENDING,
                DeploymentStatusChoices.RUNNING,
            )
            and deploy.started_at is not None
            and now - deploy.started_at
            >= timedelta(minutes=MAX_DEPLOY_TIME_MINUTE)
        ):
            handle_deployment_timeout(
                deploy=deploy,
                container_exists=exists,
                container_running=is_running,
            )
            return

        # ---------------------------------------------------------
        # 2. Running deployment
        # ---------------------------------------------------------

        if deploy.status == DeploymentStatusChoices.RUNNING:
            monitor_running_deployment(
                deploy=deploy,
                container_exists=exists,
                container_running=is_running,
            )
            return

        # ---------------------------------------------------------
        # 3. Pending deployment
        # ---------------------------------------------------------

        if deploy.status == DeploymentStatusChoices.PENDING:
            monitor_pending_deployment(
                deploy=deploy,
                container_exists=exists,
                container_running=is_running,
            )
            return

        # ---------------------------------------------------------
        # 4. Rollback
        # ---------------------------------------------------------

        if deploy.status == DeploymentStatusChoices.ROLLING_BACK:
            monitor_rollback(
                deploy=deploy,
                container_exists=exists,
                container_running=is_running,
            )


def monitor_pending_deployment(
    deploy,
    *,
    container_exists,
    container_running,
):
    """
    A pending deployment may not have a container yet.
    """

    if container_running:
        deploy.status = DeploymentStatusChoices.RUNNING
        deploy.stage = "running"
        deploy.progress = max(deploy.progress, 50)
        deploy.status_message = "Deployment container is running."
        deploy.save(
            update_fields=[
                "status",
                "stage",
                "progress",
                "status_message",
            ]
        )

        create_deploy_log(
            deploy,
            "running",
            "Deployment container is running.",
            progress=deploy.progress,
        )


def monitor_running_deployment(
    deploy,
    *,
    container_exists,
    container_running,
):
    """
    Determine whether a running deployment is still healthy.
    """

    if container_running:
        return

    if not container_exists:
        mark_deployment_failed(
            deploy,
            message="Deployment container no longer exists.",
            stage="container",
        )
        return

    mark_deployment_failed(
        deploy,
        message="Deployment container is not running.",
        stage="container",
    )


def monitor_rollback(
    deploy,
    *,
    container_exists,
    container_running,
):
    """
    Monitor rollback state.
    """

    if container_running:
        deploy.rollback_status = RollbackStatusChoices.SUCCEEDED
        deploy.status = DeploymentStatusChoices.ROLLED_BACK
        deploy.stage = "rollback_completed"
        deploy.progress = 100
        deploy.status_message = "Rollback completed successfully."

        deploy.save(
            update_fields=[
                "rollback_status",
                "status",
                "stage",
                "progress",
                "status_message",
            ]
        )

        create_deploy_log(
            deploy,
            "rollback_completed",
            "Rollback completed successfully.",
            progress=100,
        )

        return

    if not container_exists:
        deploy.rollback_status = RollbackStatusChoices.FAILED
        deploy.status = DeploymentStatusChoices.FAILED
        deploy.stage = "rollback_failed"
        deploy.error_message = (
            "Rollback failed because the deployment container "
            "does not exist."
        )

        deploy.save(
            update_fields=[
                "rollback_status",
                "status",
                "stage",
                "error_message",
            ]
        )

        create_deploy_log(
            deploy,
            "rollback_failed",
            deploy.error_message,
            level="error",
        )


def handle_deployment_timeout(
    deploy,
    *,
    container_exists,
    container_running,
):
    """
    Handle deployments that exceeded the maximum allowed time.
    """

    deploy.status = DeploymentStatusChoices.FAILED
    deploy.stage = "timeout"
    deploy.progress = min(deploy.progress, 99)
    deploy.error_message = (
        f"Deployment exceeded the maximum allowed time "
        f"of {MAX_DEPLOY_TIME_MINUTE} minutes."
    )
    deploy.status_message = "Deployment timed out."

    deploy.save(
        update_fields=[
            "status",
            "stage",
            "progress",
            "error_message",
            "status_message",
        ]
    )

    create_deploy_log(
        deploy,
        "timeout",
        deploy.error_message,
        level="error",
        event_type="deployment.timeout",
        progress=deploy.progress,
        details={
            "container_exists": container_exists,
            "container_running": container_running,
            "max_deploy_time_minutes": MAX_DEPLOY_TIME_MINUTE,
        },
    )


def mark_deployment_failed(
    deploy,
    *,
    message,
    stage,
):
    """
    Mark deployment as failed and create a corresponding event log.
    """

    deploy.status = DeploymentStatusChoices.FAILED
    deploy.stage = stage
    deploy.error_message = message
    deploy.status_message = "Deployment failed."

    deploy.save(
        update_fields=[
            "status",
            "stage",
            "error_message",
            "status_message",
        ]
    )

    create_deploy_log(
        deploy,
        stage,
        message,
        level="error",
        event_type="deployment.failed",
        progress=deploy.progress,
    )