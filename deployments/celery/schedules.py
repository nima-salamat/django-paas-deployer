
from datetime import timedelta
import os
import logging

from celery import shared_task
from celery.result import AsyncResult
from django.db import transaction
from django.utils import timezone
from core.utils import make_uuid4

from core.global_settings.config import MAX_DEPLOY_TIME_MINUTE, SERVICE_STATUS_CHOICES
from deployments.core.manager.container_manager import Container
from deploy.models import (
    Deploy,
    DeployLog,
    DeploymentStatusChoices,
    RollbackStatusChoices,
    BaseRuntimeImage,
)
from services.models import Service

from .monitoring.policies import ACTIVE_DEPLOY_STATUSES, ACTIVE_SERVICE_STATUSES, runtime_policies
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
# Stages where a container is not expected to exist yet (build / prepare).
# health_check / credentials / container_startup are excluded: by then a
# container should exist and a missing one is a real failure.
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
    "network_creation",
    "container_replacement",
    "container_creation",
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


@shared_task(bind=True, name="deployments.celery.schedules.monitor_services")
def monitor_services(self):
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
    policies = runtime_policies()
    if not policies["monitor_enabled"]:
        logger.info("Monitor disabled by operator settings")
        return {"status": "disabled"}

    # Lightweight distributed scheduler gate. Beat may pulse frequently, but
    # only one worker executes the full reconciliation at the configured cadence.
    try:
        import redis
        raw = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL") or "redis://redis:6379/0"
        r = redis.Redis.from_url(raw, decode_responses=True)
        lock_seconds = int(policies["scheduler_lock_seconds"])
        lock_key = "deployer:monitor:lock"
        run_key = "deployer:monitor:last_run"
        import time as _time
        now_ts = int(_time.time())
        last = int(r.get(run_key) or 0)
        if now_ts - last < int(policies["monitor_interval_seconds"]):
            return {"status": "throttled", "next_in": int(policies["monitor_interval_seconds"]) - (now_ts - last)}
        token = f"{self.request.id}:{now_ts}"
        if not r.set(lock_key, token, nx=True, ex=lock_seconds):
            return {"status": "locked"}
        r.set(run_key, now_ts, ex=max(lock_seconds * 3, int(policies["monitor_interval_seconds"]) * 3))
    except Exception as exc:
        logger.warning("Monitor scheduler gate unavailable: %s", exc)
        lock_key = None
        r = None
        token = None

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
    _retry_orphaned_queued_deploys()
    _reconcile_base_runtime_builds(policies)
    services = (
        Service.objects
        .select_related("selected_deploy")
        .filter(status__in=ACTIVE_SERVICE_STATUSES)[: int(policies["monitor_batch_size"])]
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
    if r is not None and lock_key and token:
        try:
            r.eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0", 1, lock_key, token)
        except Exception:
            logger.warning("Unable to release monitor scheduler lock")
    return {"status": "ok", "deployments": len(deployments), "services": len(services)}


def _retry_orphaned_queued_deploys() -> None:
    """Re-enqueue deployments whose DB transaction committed but Celery did not.

    This makes Redis/Celery outages non-fatal to the API request: the operation
    stays QUEUED/PENDING and is picked up automatically once the broker returns.
    """
    from deployments.celery.tasks import deploy as app_deploy, run_db_deploy
    from deployments.core.db_deployer import DB_PLATFORMS
    from deployments.common import parse_config

    policies = runtime_policies()
    if not policies["recovery_enabled"]:
        return
    cutoff = timezone.now() - timedelta(seconds=int(policies["stale_worker_seconds"]))
    candidates = (
        Deploy.objects
        .select_related("service", "service__plan")
        .filter(status=DeploymentStatusChoices.PENDING, created_at__lt=cutoff)
        .order_by("created_at")[: int(runtime_policies()["monitor_batch_size"])]
    )
    for deploy in candidates:
        service = deploy.service
        if service is None or service.status != SERVICE_STATUS_CHOICES.QUEUED:
            continue
        lock_id = make_uuid4()
        try:
            # Bound automatic recovery per deployment so a permanently broken
            # broker/task does not create an infinite requeue loop.
            import redis as _redis
            raw = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL") or "redis://redis:6379/0"
            rr = _redis.Redis.from_url(raw, decode_responses=True)
            recovery_key = f"deployer:recovery:deployment:{deploy.pk}"
            attempts = int(rr.get(recovery_key) or 0)
            if attempts >= int(policies["max_recovery_attempts"]):
                logger.error("Recovery limit reached for deployment %s", deploy.pk)
                continue
            rr.incr(recovery_key)
            rr.expire(recovery_key, max(3600, int(policies["stale_worker_seconds"]) * 10))
            cfg = parse_config(deploy.config) if isinstance(deploy.config, dict) else {}
            platform = str(
                cfg.get("platform")
                or getattr(getattr(service, "plan", None), "platform", "")
                or ""
            ).strip().lower()
            task = run_db_deploy if platform in DB_PLATFORMS else app_deploy
            task.apply_async(args=[str(deploy.id)], task_id=lock_id)
            Deploy.objects.filter(pk=deploy.pk, status=DeploymentStatusChoices.PENDING).update(
                status_message="Deployment re-queued after temporary broker unavailability.",
            )
            service.__class__.objects.filter(
                pk=service.pk, status=SERVICE_STATUS_CHOICES.QUEUED
            ).update(task_id=lock_id)
            logger.info("Re-queued orphaned deployment %s with task_id=%s", deploy.pk, lock_id)
        except Exception:
            logger.warning(
                "Unable to re-queue deployment %s; broker may still be unavailable.",
                deploy.pk, exc_info=True,
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
            if minutes_elapsed >= int(policies["deploy_timeout_minutes"]):
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
                    or progress < 85
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
                if minutes_elapsed >= int(policies["queued_timeout_minutes"]):
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
                if minutes_elapsed >= int(policies["stop_timeout_minutes"]):
                    try:
                        container.stop(timeout=5)
                        container.remove()
                    except Exception as exc:
                        logger.warning("Force stop failed for '%s': %s", container_name, exc)
                    mark_service_stopped(locked, deploy=deploy)
            return


# ---- (removed old handlers, replaced by monitoring.actions) ----


def _reconcile_base_runtime_builds(policies: dict) -> None:
    """Recover base-image rows whose builder disappeared or exceeded the operator timeout."""
    cutoff = timezone.now() - timedelta(minutes=int(policies["stale_base_build_minutes"]))
    stale = BaseRuntimeImage.objects.filter(
        status=BaseRuntimeImage.Status.BUILDING,
        build_started_at__lt=cutoff,
    ).order_by("build_started_at")[: int(policies["monitor_batch_size"])]
    for row in stale:
        try:
            updated = BaseRuntimeImage.objects.filter(
                pk=row.pk, status=BaseRuntimeImage.Status.BUILDING, build_started_at__lt=cutoff
            ).update(
                status=BaseRuntimeImage.Status.FAILED,
                build_task_id="",
                build_owner_deployment_id="",
                last_error="Base image build marked stale by monitor.",
                build_completed_at=timezone.now(),
                updated_at=timezone.now(),
            )
            if updated and policies["recovery_enabled"]:
                # A later deployment/admin rebuild can safely claim the row again.
                logger.warning("Recovered stale base-image build row %s (%s)", row.pk, row.image_ref)
        except Exception:
            logger.exception("Failed to reconcile stale base-image row %s", row.pk)
