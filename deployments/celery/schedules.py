
from datetime import timedelta
import logging

from celery import shared_task
from celery.result import AsyncResult
from django.db import transaction
from django.utils import timezone

from core.global_settings.config import MAX_DEPLOY_TIME_MINUTE, SERVICE_STATUS_CHOICES
from deployments.core.manager.container_manager import Container
from deploy.models import (
    Deploy,
    DeployLog,
    DeploymentStatusChoices,
    RollbackStatusChoices,
)
from services.models import Service

from .monitoring.policies import (
    DEPLOY_TIMEOUT_MINUTES,
    STUCK_QUEUED_MINUTES,
    STOP_TIMEOUT_MINUTES,
    UNEXPECTED_DEATH_GRACE_SECONDS,
    ACTIVE_DEPLOY_STATUSES,
    ACTIVE_SERVICE_STATUSES,
)
from .monitoring.actions import (
    mark_service_running,
    mark_service_stopped,
    mark_service_failed,
    mark_deploy_failed,
    mark_deploy_timeout,
    mark_rollback_complete,
    mark_rollback_failed,
)

logger = logging.getLogger(__name__)

# Stages where a container is not expected yet OR is still initialising
# (MySQL/MariaDB official entrypoint can take 30-120 s after the container
# is "running").  Monitor must NOT fail the deploy for a missing /
# non-running container during these stages.
PRE_CONTAINER_STAGES = frozenset({
    "",
    "idle",
    "starting",
    "validation",
    "prepare_resources",
    "platform_detection",
    "entrypoint_detection",
    "image_build",
    "dockerfile",
    "state_snapshot",
    "cancelled",
    "image_pull",
    "volume_creation",
    "container_replacement",
    "container_creation",
    "container_startup",
    "health_check",
    "credentials",
})



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
    Dual-scan monitor reconciling three truths:
      1) Deploy.status (DB)
      2) Service.status (DB)
      3) Docker container reality

    Two independent scans:
      A. Active deployments (pending, running, rolling_back)
      B. Services needing runtime reconciliation (queued, deploying, running,
         stopping, succeeded)
    """
    # ------------------------------------------------------------------
    # 1. Active deployments (pipeline progress / timeout)
    # ------------------------------------------------------------------
    deployments = (
        Deploy.objects
        .select_related("service")
        .filter(status__in=ACTIVE_DEPLOY_STATUSES)
    )
    for deploy in deployments:
        try:
            _reconcile_active_deploy(deploy)
        except Exception:
            logger.exception("Monitor error for deployment %s", deploy.pk)

    # ------------------------------------------------------------------
    # 2. Services that need runtime reconciliation
    # ------------------------------------------------------------------
    services = (
        Service.objects
        .select_related("selected_deploy")
        .filter(status__in=ACTIVE_SERVICE_STATUSES)
    )
    for service in services:
        try:
            _reconcile_service_runtime(service)
        except Exception:
            logger.exception("Monitor error for service %s", service.pk)

    logger.info(
        "Monitor tick completed (deployments=%s, services=%s)",
        len(deployments),
        len(services),
        extra={"event": "monitor_tick", "deployments": len(deployments), "services": len(services)},
    )


def _reconcile_active_deploy(deploy: Deploy) -> None:
    """
    Reconcile a single deployment in pipeline (pending/running/rolling_back).

    Rules:
      - pending + container running → running
      - pending + timeout → failed (deploy + service)
      - running + container missing → failed
      - running + container not running → failed
      - rolling_back + container running → rollback complete
      - rolling_back + container missing → rollback failed
    """
    container_name = deploy.service.get_docker_service_name()
    container = Container(container_name)

    try:
        runtime = container.inspect_runtime()
        exists = runtime.get("exists", False)
        is_running = runtime.get("running", False)
        status_raw = runtime.get("status", "missing")
        exit_code = runtime.get("exit_code")
    except Exception as exc:
        logger.warning("Failed to inspect container '%s': %s", container_name, exc)
        exists = False
        is_running = False
        status_raw = "error"

    now = timezone.now()

    with transaction.atomic():
        locked = (
            Deploy.objects
            .select_related("service")
            .select_for_update()
            .filter(pk=deploy.pk)
            .first()
        )
        if not locked:
            return
        if locked.status not in ACTIVE_DEPLOY_STATUSES:
            return  # already terminal, skip

        service = locked.service

        # 1. Timeout check
        if locked.status in ("pending", "running") and locked.started_at:
            minutes_elapsed = (now - locked.started_at).total_seconds() / 60.0
            if minutes_elapsed >= DEPLOY_TIMEOUT_MINUTES:
                mark_deploy_timeout(
                    deploy=locked,
                    container_exists=exists,
                    container_running=is_running,
                )
                return

        # 2. Pending deployment
        if locked.status == DeploymentStatusChoices.PENDING:
            if is_running:
                locked.status = DeploymentStatusChoices.RUNNING
                locked.stage = "running"
                locked.progress = max(locked.progress, 50)
                locked.status_message = "Container is running."
                locked.save(
                    update_fields=["status", "stage", "progress", "status_message"]
                )
                create_deploy_log(
                    locked,
                    stage="running",
                    message="Deployment container is running.",
                    progress=locked.progress,
                )
            return

        # 3. Running deployment
        # IMPORTANT: Deploy.status is set to RUNNING as soon as the Celery task
        # starts — long before a container exists (image build can take minutes).
        # Only treat a missing/dead container as failure once we are past the
        # build/prepare stages (or progress indicates container should exist).
        if locked.status == DeploymentStatusChoices.RUNNING:
            if not is_running:
                stage_name = (locked.stage or "").strip().lower()
                progress = int(locked.progress or 0)
                still_building = (
                    stage_name in PRE_CONTAINER_STAGES
                    or progress < 95
                )
                if still_building:
                    # Let the worker finish; timeout handler covers stuck builds.
                    logger.debug(
                        "Deploy %s still in pre-container stage=%s progress=%s; "
                        "skipping missing-container fail",
                        locked.pk,
                        stage_name,
                        progress,
                    )
                    return

                stage = "container_missing" if not exists else "container_not_running"
                message = (
                    "Deployment container no longer exists."
                    if not exists
                    else f"Deployment container is not running (status: {status_raw})."
                )
                mark_deploy_failed(
                    deploy=locked,
                    message=message,
                    stage=stage,
                    details={
                        "container_exists": exists,
                        "container_status": status_raw,
                        "exit_code": exit_code,
                        "deploy_stage": stage_name,
                        "deploy_progress": progress,
                    },
                )
            return

        # 4. Rollback
        if locked.status == DeploymentStatusChoices.ROLLING_BACK:
            if is_running:
                mark_rollback_complete(locked)
            else:
                mark_rollback_failed(locked)
            return


def _reconcile_service_runtime(service: Service) -> None:
    """
    Reconcile a service's DB status against the real container state.

    This scan catches container death after deploy succeeded, stuck
    queued/deploying/stopping services, and unexpected container loss.

    Rules:
      - succeeded + container running → running
      - succeeded + container dead → failed (or stopped if user initiated)
      - queued/deploying + container running → running
      - queued/deploying + timeout → failed
      - running + container not running → failed
      - stopping + container not running → stopped
      - stopping + timeout → failed (force stop/remove)
    """
    container_name = service.get_docker_service_name()
    container = Container(container_name)

    try:
        runtime = container.inspect_runtime()
        exists = runtime.get("exists", False)
        is_running = runtime.get("running", False)
        status_raw = runtime.get("status", "missing")
        exit_code = runtime.get("exit_code")
    except Exception as exc:
        logger.warning("Failed to inspect container '%s': %s", container_name, exc)
        exists = False
        is_running = False
        status_raw = "error"

    now = timezone.now()
    deploy = service.selected_deploy  # may be None

    with transaction.atomic():
        # Do NOT select_related("selected_deploy") with select_for_update:
        # selected_deploy is nullable → LEFT OUTER JOIN → Postgres rejects
        # FOR UPDATE on the nullable side of an outer join.
        locked = (
            Service.objects
            .select_for_update()
            .filter(pk=service.pk)
            .first()
        )
        if not locked:
            return
        if locked.status not in ACTIVE_SERVICE_STATUSES:
            return  # terminal or not monitored

        # Load selected deploy separately (no FOR UPDATE on the join)
        deploy = locked.selected_deploy  # may be None; simple FK access

        # ------------------------------------------------------------------
        # RUNNING (or SUCCEEDED legacy) → verify container is still up
        # ------------------------------------------------------------------
        if locked.status in (SERVICE_STATUS_CHOICES.RUNNING, SERVICE_STATUS_CHOICES.SUCCEEDED):
            if not is_running:
                message = f"Service container is not running (status: {status_raw})."
                mark_service_failed(
                    service=locked,
                    message=message,
                    deploy=deploy,
                    details={
                        "container_exists": exists,
                        "container_status": status_raw,
                        "exit_code": exit_code,
                    },
                )
            elif locked.status == SERVICE_STATUS_CHOICES.SUCCEEDED:
                # Legacy succeeded row — upgrade to running
                mark_service_running(locked, deploy=deploy)
            return

        # ------------------------------------------------------------------
        # QUEUED / DEPLOYING
        # ------------------------------------------------------------------
        if locked.status in (SERVICE_STATUS_CHOICES.QUEUED, SERVICE_STATUS_CHOICES.DEPLOYING):
            # Stuck timeout
            if locked.deploy_started:
                minutes_elapsed = (now - locked.deploy_started).total_seconds() / 60.0
                if minutes_elapsed >= STUCK_QUEUED_MINUTES:
                    mark_service_failed(
                        service=locked,
                        message="Service stuck in queue/deploying beyond timeout.",
                        deploy=deploy,
                        details={
                            "container_exists": exists,
                            "container_running": is_running,
                            "elapsed_minutes": round(minutes_elapsed, 1),
                        },
                    )
                    return

            # Container already running → transition to running
            if is_running:
                mark_service_running(locked, deploy=deploy)
            return

        # ------------------------------------------------------------------
        # STOPPING
        # ------------------------------------------------------------------
        if locked.status == SERVICE_STATUS_CHOICES.STOPPING:
            if not is_running:
                mark_service_stopped(locked, deploy=deploy)
                return

            # Stop timeout — container still running after grace period
            if locked.deploy_started:
                minutes_elapsed = (now - locked.deploy_started).total_seconds() / 60.0
                if minutes_elapsed >= STOP_TIMEOUT_MINUTES:
                    try:
                        container.stop(timeout=5)
                        container.remove()
                    except Exception as exc:
                        logger.warning("Force stop failed for '%s': %s", container_name, exc)
                    mark_service_stopped(locked, deploy=deploy)
            return


# ---- (removed old handlers, replaced by monitoring.actions) ----
