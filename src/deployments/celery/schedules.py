
from datetime import timedelta
import os
import logging
import uuid

from celery import shared_task
from celery.result import AsyncResult
from django.db import transaction
from django.utils import timezone
from core.utils import make_uuid4

from core.global_settings.config import MAX_DEPLOY_TIME_MINUTE, SERVICE_STATUS_CHOICES
from deployments.core.manager.container_manager import Container
from deployments.core.swarm import SwarmRuntime, swarm_enabled
from deployments.core.state.manager import StateManager
from deploy.models import (
    Deploy,
    DeployLog,
    DeploymentStatusChoices,
    RollbackStatusChoices,
    BaseRuntimeImage,
)
from services.models import Service
from services.lifecycle.authority import get_authoritative_deploy
from services.revisioning import activate_revision_locked
from services.revisioning import ensure_revision_for_deploy, get_active_deploy, materialize_revision_config

from .monitoring.policies import ACTIVE_DEPLOY_STATUSES, ACTIVE_SERVICE_STATUSES, runtime_policies
from deployments.planning import ConfigurationResolver, DeploymentPlanCompiler
from deployments.common.resource_policy import runtime_limits
from deployments.reconciliation import (
    DesiredRuntimeState,
    ReconciliationAction,
    ReconciliationExecutionContext,
    ReconciliationExecutor,
    ReconciliationPlanner,
)
from deployments.runtime import RuntimeIdentity, RuntimeHandle
from deployments.infrastructure.django_runtime import DjangoRuntimeSelectionResolver
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
# Docker Swarm can transiently report zero running replicas while an
# on-failure restart is between task attempts. Treat those states as degraded,
# not terminal, until no desired-running task remains in a non-terminal state.
SWARM_TRANSIENT_TASK_STATES = frozenset({
    "new", "pending", "assigned", "accepted",
    "preparing", "ready", "starting", "running",
})
SWARM_TERMINAL_TASK_STATES = frozenset({
    "failed", "rejected", "shutdown", "orphaned",
})

def _swarm_has_terminal_runtime_failure(state) -> bool:
    """True only when Swarm has no active restart/update path left."""
    if state is None:
        return True
    update_state = str(getattr(state, "update_state", "") or "").lower()
    if update_state in {"updating", "rollback_started", "rollback_paused"}:
        return False
    if update_state == "rollback_completed":
        return True

    desired = [
        task for task in (getattr(state, "tasks", ()) or ())
        if str(getattr(task, "desired_state", "") or "").lower() == "running"
    ]
    if not desired:
        # A desired-one service with an on-failure/any restart policy may be in
        # the gap between task attempts. Let Swarm create its replacement.
        restart_condition = str(
            getattr(state, "restart_condition", "") or ""
        ).lower()
        if restart_condition in {"on-failure", "any"}:
            return False
        return state.replicas_desired > 0

    if any(
        str(getattr(task, "state", "") or "").lower() in SWARM_TRANSIENT_TASK_STATES
        for task in desired
    ):
        return False

    if (
        str(getattr(state, "restart_condition", "") or "").lower()
        in {"on-failure", "any"}
        and any(
            str(getattr(task, "state", "") or "").lower() in SWARM_TERMINAL_TASK_STATES
            for task in desired
        )
    ):
        # The desired replica has a restart policy and a failed task is
        # present. Treat the interval before the replacement as a transient
        # runtime condition; once MaxAttempts is exhausted Swarm removes the
        # desired-running task and the no-desired branch above becomes terminal.
        return False

    return all(
        str(getattr(task, "state", "") or "").lower() in SWARM_TERMINAL_TASK_STATES
        for task in desired
    )

def _swarm_failure_details(runtime, service_name: str, state) -> dict:
    details = {
        "runtime": "docker-swarm",
        "service": service_name,
        "replicas_desired": getattr(state, "replicas_desired", 0) if state else 0,
        "replicas_running": getattr(state, "replicas_running", 0) if state else 0,
        "update_state": getattr(state, "update_state", None) if state else None,
        "update_message": getattr(state, "update_message", None) if state else None,
        "tasks": [
            {
                "task_id": task.task_id,
                "desired_state": task.desired_state,
                "state": task.state,
                "node_id": task.node_id,
                "node_name": task.node_name,
                "error": task.error,
                "message": task.message,
                "image": task.image,
            }
            for task in (getattr(state, "tasks", ()) or ())
        ],
    }
    try:
        raw = runtime.service_logs(service_name, tail=100)
        details["service_logs"] = (
            raw.decode("utf-8", "replace")
            if isinstance(raw, (bytes, bytearray))
            else str(raw or "")
        )[-12000:]
    except Exception as exc:
        details["service_logs"] = f"<log collection failed: {exc}>"
    return details

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
    "cancel_requested",
    "timeout_requested",
    "image_pull",
    "volume_creation",
    "network_creation",
    "container_replacement",
    "container_creation",
})



@shared_task(name="deployments.celery.schedules.sync_swarm_infrastructure")
def sync_swarm_infrastructure():
    if not swarm_enabled():
        return {"status": "disabled"}
    try:
        from deployments.core.swarm import sync_swarm_nodes
        return sync_swarm_nodes()
    except Exception as exc:
        logger.exception("Swarm infrastructure synchronization failed: %s", exc)
        return {"status": "error", "error": str(exc)}


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
    """Persist a scheduler event through the durable deployment outbox."""
    try:
        from deployments.core.sink import DBAndChannelEventSink
        from deployments.core.types import DeploymentEvent

        event_details = {
            **(details or {}),
            "event_type": event_type,
        }
        if exception_type:
            event_details["exception_type"] = exception_type
        if traceback:
            event_details["traceback"] = traceback

        DBAndChannelEventSink(deploy.pk)(
            DeploymentEvent(
                stage=stage,
                message=message,
                level=level,
                progress=progress,
                details=event_details,
            )
        )
    except Exception:
        logger.exception(
            "Failed to persist durable scheduler event for deploy %s stage=%s",
            getattr(deploy, "pk", "?"),
            stage,
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
        # The monitor is a mutating reconciliation loop. If its distributed
        # coordination store is unavailable, running anyway allows every worker
        # to reconcile the same Swarm resources concurrently.
        logger.warning(
            "Monitor scheduler gate unavailable; skipping mutation tick: %s",
            exc,
        )
        return {
            "status": "scheduler_unavailable",
            "error": str(exc)[:500],
        }

    # Finalize cancellations that never reached a worker. This is especially
    # important for timeout requests raised while a deployment is still pending.
    _finalize_pending_cancellations()

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
    _recover_stale_running_deploys(policies)
    _reconcile_base_runtime_builds(policies)
    services = (
        Service.objects
        .select_related("active_revision")
        .filter(status__in=ACTIVE_SERVICE_STATUSES)[: int(policies["monitor_batch_size"])]
    )
    for service in services:
        try:
            if _reconcile_desired_state(service):
                continue
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



def _finalize_pending_cancellations() -> None:
    """Terminalize pending deployments cancelled before their worker started."""
    candidates = (
        Deploy.objects
        .select_related("service")
        .filter(
            status=DeploymentStatusChoices.PENDING,
            cancel_requested=True,
        )
        .order_by("updated_at")[: int(runtime_policies()["monitor_batch_size"])]
    )
    for deploy in candidates:
        try:
            StateManager.finalize_pending_cancellation(
                deploy.pk,
                message=deploy.error_message or "Deployment was cancelled before execution.",
            )
            service = deploy.service
            if service and service.status == SERVICE_STATUS_CHOICES.QUEUED:
                StateManager.transition_service(
                    service.pk,
                    SERVICE_STATUS_CHOICES.STOPPED,
                    update_fields={"desired_state": "stopped"},
                )
            logger.info("Finalized pre-start cancellation for deployment %s", deploy.pk)
        except Exception:
            logger.exception("Failed to finalize pending cancellation for deployment %s", deploy.pk)

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
        .filter(
            status=DeploymentStatusChoices.PENDING,
            cancel_requested=False,
            updated_at__lt=cutoff,
        )
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
                execution_task_id=lock_id,
                worker_heartbeat_at=None,
                updated_at=timezone.now(),
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



def _recover_stale_running_deploys(policies) -> None:
    if swarm_enabled():
        return _recover_stale_running_deploys_swarm(policies)
    """Converge stale workers only when external resources prove ownership.

    A service keeps its previous container under the canonical name during
    image build, so inspecting only ``container running/healthy`` is unsafe: it
    can describe the *previous* release rather than the stale deployment.
    """
    stale_after = int(policies.get("stale_worker_seconds", 120))
    cutoff = timezone.now() - timedelta(seconds=max(stale_after * 2, 60))
    candidates = (
        Deploy.objects.select_related("service")
        .filter(
            status=DeploymentStatusChoices.RUNNING,
            worker_heartbeat_at__isnull=False,
            worker_heartbeat_at__lt=cutoff,
        )
        .order_by("worker_heartbeat_at")[: int(policies.get("monitor_batch_size", 50))]
    )
    for deploy in candidates:
        try:
            service_name = deploy.service.get_docker_service_name()
            container = Container(service_name)
            runtime = container.inspect_runtime()
            labels = container.get_labels() if runtime.get("exists") else {}

            with transaction.atomic():
                locked = (
                    Deploy.objects.select_for_update().select_related("service")
                    .filter(pk=deploy.pk).first()
                )
                if not locked or locked.status != DeploymentStatusChoices.RUNNING:
                    continue
                if locked.worker_heartbeat_at and locked.worker_heartbeat_at >= cutoff:
                    continue

                owner_task = str(locked.execution_task_id or "")
                service = locked.service
                if owner_task and str(service.task_id or "") not in (owner_task, ""):
                    logger.info("Skipping stale recovery for deploy=%s; service is now owned by task=%s", locked.pk, service.task_id)
                    continue

                owned_by_deploy = str(labels.get("deployment.id") or "") == str(locked.pk)
                stage = (locked.stage or "").strip().lower()

                # Only the activation boundary proves that readiness has already
                # completed. A healthy canonical-name container during build/start
                # may still be the previous release.
                if owned_by_deploy and stage == "activation" and runtime.get("running") and runtime.get("health") in (None, "healthy"):
                    try:
                        locked = ensure_revision_for_deploy(locked)
                    except Exception:
                        logger.exception("Could not materialize revision for stale deployment %s", locked.pk)
                        continue
                    current_active = get_authoritative_deploy(service)
                    current_selected = current_active.pk if current_active else None
                    if current_selected != locked.pk:
                        expected_previous = locked.previous_deploy_id
                        if current_selected != expected_previous:
                            logger.warning(
                                "Refusing stale activation recovery for deploy=%s: active deploy changed from expected=%s to=%s",
                                locked.pk, expected_previous, current_selected,
                            )
                            continue
                        activate_revision_locked(service, locked.revision_id)

                    StateManager.transition_deploy_system_terminal(
                        locked.pk,
                        DeploymentStatusChoices.SUCCEEDED,
                        update_fields={
                            "stage": "deployment_completed",
                            "progress": 100,
                            "status_message": "Deployment recovered after worker interruption; activation had already completed.",
                            "error_message": "",
                            "health_status": "healthy",
                            "container_status": "running",
                        },
                        event_payload={
                            "event_id": str(uuid.uuid4()),
                            "trace_id": str(locked.pk),
                            "deployment_id": str(locked.pk),
                            "service_id": str(locked.service_id),
                            "revision_id": str(getattr(locked, "revision_id", "") or ""),
                            "task_id": "stale-recovery",
                            "event_type": "deployment.deployment_completed.info",
                            "stage": "deployment_completed",
                            "level": "info",
                            "message": "Deployment recovered after worker interruption; activation had already completed.",
                            "progress": 100,
                            "details": {"controlled_by": "stale_recovery", "health_status": "healthy"},
                        },
                    )
                    StateManager.transition_service(
                        locked.service_id, SERVICE_STATUS_CHOICES.RUNNING,
                        update_fields={"deployed_at": timezone.now(), "deploy_started": None, "task_id": None},
                    )
                    logger.warning("Recovered stale activated deploy %s as succeeded.", locked.pk)
                    continue

                # If the canonical container belongs to the stale deployment
                # but activation has not been committed, remove only that
                # replacement and attempt to restore the recorded previous
                # deployment resource. Never touch an unrelated/newer resource.
                if owned_by_deploy and stage in {"container_creation", "container_startup", "health_check"}:
                    if runtime.get("exists"):
                        try:
                            container.stop(timeout=5)
                        except Exception:
                            pass
                        try:
                            container.remove()
                        except Exception as exc:
                            logger.warning("Failed to remove stale replacement container for deploy=%s: %s", locked.pk, exc)

                    restored = False
                    previous_id = locked.previous_deploy_id
                    if previous_id:
                        previous_resources = Container.find_owned(
                            deployment_id=str(previous_id), service_id=str(service.pk), all=True,
                        )
                        for previous in previous_resources:
                            try:
                                previous_name = previous.name
                                previous_obj = Container(previous_name)
                                previous_obj.rename(service_name)
                                restored = True
                                break
                            except Exception as exc:
                                logger.warning("Unable to restore previous deployment resource %s: %s", previous.name, exc)
                    if restored:
                        logger.warning("Rolled back stale deploy %s to previous deployment %s.", locked.pk, previous_id)
                        StateManager.transition_deploy_system_terminal(
                            locked.pk,
                            DeploymentStatusChoices.ROLLED_BACK,
                            update_fields={
                                "stage": "rollback",
                                "progress": 100,
                                "status_message": "Deployment worker stopped before activation; previous deployment restored.",
                                "error_message": "",
                            },
                            event_payload={
                                "event_id": str(uuid.uuid4()),
                                "trace_id": str(locked.pk),
                                "deployment_id": str(locked.pk),
                                "service_id": str(locked.service_id),
                                "revision_id": str(getattr(locked, "revision_id", "") or ""),
                                "task_id": "stale-recovery",
                                "event_type": "deployment.rollback.info",
                                "stage": "rollback",
                                "level": "info",
                                "message": "Deployment worker stopped before activation; previous deployment restored.",
                                "progress": 100,
                                "details": {"controlled_by": "stale_recovery", "previous_deploy_id": str(previous_id or "")},
                            },
                        )
                        StateManager.transition_service(
                            locked.service_id, SERVICE_STATUS_CHOICES.RUNNING,
                            update_fields={"deployed_at": timezone.now(), "deploy_started": None, "task_id": None},
                        )
                    else:
                        message = (
                            "Deployment worker stopped before activation and the previous deployment "
                            "could not be restored automatically."
                        )
                        StateManager.transition_deploy_system_terminal(
                            locked.pk,
                            DeploymentStatusChoices.FAILED,
                            update_fields={
                                "stage": "worker_lost",
                                "progress": 100,
                                "status_message": message,
                                "error_message": message,
                            },
                            event_payload={
                                "event_id": str(uuid.uuid4()),
                                "trace_id": str(locked.pk),
                                "deployment_id": str(locked.pk),
                                "service_id": str(locked.service_id),
                                "revision_id": str(getattr(locked, "revision_id", "") or ""),
                                "task_id": "stale-recovery",
                                "event_type": "deployment.worker_lost.error",
                                "stage": "worker_lost",
                                "level": "error",
                                "message": message,
                                "progress": 100,
                                "details": {"controlled_by": "stale_recovery", "previous_deploy_id": str(previous_id or "")},
                            },
                        )
                        StateManager.transition_service(
                            locked.service_id, SERVICE_STATUS_CHOICES.FAILED,
                            update_fields={"deploy_started": None, "task_id": None},
                        )
                    continue

                # Pre-container or otherwise ambiguous crashes are never inferred
                # as success from the old canonical container. Fail closed.
                message = (
                    "Deployment worker stopped responding before activation. "
                    "The platform could not prove that the replacement deployment became active."
                )
                StateManager.transition_deploy_system_terminal(
                    locked.pk,
                    DeploymentStatusChoices.FAILED,
                    update_fields={
                        "stage": "worker_lost",
                        "progress": 100,
                        "status_message": message,
                        "error_message": message,
                        "health_status": runtime.get("health") or "unknown",
                        "container_status": runtime.get("status") or "unknown",
                    },
                    event_payload={
                        "event_id": str(uuid.uuid4()),
                        "trace_id": str(locked.pk),
                        "deployment_id": str(locked.pk),
                        "service_id": str(locked.service_id),
                        "revision_id": str(getattr(locked, "revision_id", "") or ""),
                        "task_id": "stale-recovery",
                        "event_type": "deployment.worker_lost.error",
                        "stage": "worker_lost",
                        "level": "error",
                        "message": message,
                        "progress": 100,
                        "details": {
                            "controlled_by": "stale_recovery",
                            "health_status": runtime.get("health") or "unknown",
                            "container_status": runtime.get("status") or "unknown",
                        },
                    },
                )
                if service.status not in (SERVICE_STATUS_CHOICES.STOPPED, SERVICE_STATUS_CHOICES.FAILED):
                    StateManager.transition_service(
                        locked.service_id, SERVICE_STATUS_CHOICES.FAILED,
                        update_fields={"deploy_started": None, "task_id": None},
                    )
                logger.error("Marked stale deploy %s failed without inferring success from an unrelated container.", locked.pk)
        except Exception:
            logger.exception("Stale deployment recovery failed for deploy=%s", deploy.pk)



def _recover_stale_running_deploys_swarm(policies) -> None:
    """Recover stale workers from the Swarm service/task state."""
    stale_after = int(policies.get("stale_worker_seconds", 120))
    cutoff = timezone.now() - timedelta(seconds=max(stale_after * 2, 60))
    candidates = (
        Deploy.objects.select_related("service", "revision")
        .filter(
            status=DeploymentStatusChoices.RUNNING,
            worker_heartbeat_at__isnull=False,
            worker_heartbeat_at__lt=cutoff,
        )
        .order_by("worker_heartbeat_at")[: int(policies.get("monitor_batch_size", 50))]
    )
    runtime = SwarmRuntime()
    for deploy in candidates:
        try:
            service_name = deploy.service.get_docker_service_name()
            state = runtime.inspect_service(service_name)
            if state is None or state.replicas_running != 1:
                continue
            docker_service = runtime.client.services.get(service_name)
            labels = ((docker_service.attrs or {}).get("Spec") or {}).get("Labels") or {}
            if str(labels.get("passdeployer.deployment") or "") != str(deploy.pk):
                continue
            with transaction.atomic():
                locked = Deploy.objects.select_for_update().select_related("service").filter(pk=deploy.pk).first()
                if not locked or locked.status != DeploymentStatusChoices.RUNNING:
                    continue
                if str(getattr(locked.service, "desired_state", "stopped") or "stopped").lower() != "running":
                    logger.info(
                        "Skipping stale Swarm recovery for deploy=%s because service desired_state is %s.",
                        locked.pk,
                        locked.service.desired_state,
                    )
                    continue
                revision = ensure_revision_for_deploy(locked)
                current = get_authoritative_deploy(locked.service)
                if current is not None and current.pk != locked.pk:
                    logger.warning("Refusing stale Swarm recovery for deploy=%s; active deploy=%s", locked.pk, current.pk)
                    continue
                committed = StateManager.activate_revision_and_succeed(
                    locked.pk,
                    revision.revision_id,
                    task_id=locked.execution_task_id or None,
                    update_fields={
                        "stage": "deployment_completed",
                        "progress": 100,
                        "status_message": "Deployment recovered from a running Swarm service after worker interruption.",
                        "error_message": "",
                        "health_status": "running",
                        "container_status": "running",
                    },
                    event_payload={
                        "event_id": str(uuid.uuid4()),
                        "trace_id": str(locked.pk),
                        "deployment_id": str(locked.pk),
                        "service_id": str(locked.service_id),
                        "revision_id": str(getattr(locked, "revision_id", "") or ""),
                        "task_id": "stale-recovery",
                        "event_type": "deployment.deployment_completed.info",
                        "stage": "deployment_completed",
                        "level": "info",
                        "message": "Deployment recovered from a running Swarm service after worker interruption.",
                        "progress": 100,
                        "details": {"controlled_by": "stale_recovery", "health_status": "running"},
                    },
                )
                if not committed:
                    logger.info("Refusing stale Swarm recovery success for deploy=%s", locked.pk)
                    continue
                StateManager.transition_service(
                    locked.service_id, SERVICE_STATUS_CHOICES.RUNNING,
                    update_fields={"deployed_at": timezone.now(), "deploy_started": None, "task_id": None},
                )
        except Exception:
            logger.exception("Swarm stale deployment recovery failed for deploy=%s", deploy.pk)

def _reconcile_active_deploy(deploy: Deploy) -> None:
    if swarm_enabled():
        return _reconcile_active_deploy_swarm(deploy)
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
        if locked.cancel_requested:
            # Cancellation/timeout is owned by the deployment worker. Do not
            # let the monitor race it by declaring a second terminal failure.
            return

        service = locked.service

        # 1. Timeout check. The phase deadline is authoritative:
        # base-image wait has its own budget; application work gets a fresh
        # deployment budget after base readiness.
        if locked.status == "running":
            from deploy.base_images import deployment_phase_remaining_seconds
            remaining = deployment_phase_remaining_seconds(locked, now=now)
            if remaining is not None and remaining <= 0:
                mark_deploy_timeout(
                    deploy=locked,
                    container_exists=exists,
                    container_running=is_running,
                )
                return

        # 2. Pending deployment
        if locked.status == DeploymentStatusChoices.PENDING:
            if is_running:
                StateManager.transition_deploy(
                    locked.pk,
                    DeploymentStatusChoices.RUNNING,
                    update_fields={
                        "stage": "running",
                        "progress": max(locked.progress, 50),
                        "status_message": "Container is running.",
                    },
                )
                refreshed = Deploy.objects.get(pk=locked.pk)
                create_deploy_log(
                    refreshed,
                    stage="running",
                    message="Deployment container is running.",
                    progress=refreshed.progress,
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



def _reconcile_active_deploy_swarm(deploy: Deploy) -> None:
    runtime = SwarmRuntime()
    service_name = deploy.service.get_docker_service_name()
    try:
        state = runtime.inspect_service(service_name)
    except Exception as exc:
        # An unavailable Docker API is an observation failure, not evidence
        # that the application runtime is gone. Never mark the deployment
        # terminal solely because this monitor tick could not inspect Swarm.
        logger.warning("Failed to inspect Swarm service '%s': %s", service_name, exc)
        return
    if state is None:
        # The service can legitimately be missing during a user-driven stop or
        # an in-flight replacement. The lifecycle worker owns such mutations.
        return
    running = bool(state.replicas_running == 1)
    now = timezone.now()
    with transaction.atomic():
        locked = Deploy.objects.select_for_update().select_related("service").filter(pk=deploy.pk).first()
        if not locked or locked.status not in ACTIVE_DEPLOY_STATUSES or locked.cancel_requested:
            return
        labels = dict(getattr(state, "labels", {}) or {})
        observed_release = str(labels.get("release.id") or "")
        observed_revision = str(labels.get("revision.id") or "")
        # Native Swarm runtime labels use the reusable Release primary key.
        # Deploy.release_id is only the historical per-attempt UUID.
        expected_release = str(
            getattr(locked, "release_reference_id", None)
            or getattr(locked, "release_id", "")
            or ""
        )
        expected_revision = str(getattr(locked, "revision_id", "") or "")
        if expected_release and observed_release and observed_release != expected_release:
            current = {
                "reconciliation_required": True,
                "status_message": "Runtime release identity differs from the authoritative deployment.",
            }
            Deploy.objects.filter(pk=locked.pk).update(**current)
            logger.warning("Runtime release drift for deploy=%s expected=%s observed=%s", locked.pk, expected_release, observed_release)
            return
        if expected_revision and observed_revision and observed_revision != expected_revision:
            Deploy.objects.filter(pk=locked.pk).update(
                reconciliation_required=True,
                status_message="Runtime revision identity differs from the authoritative deployment.",
                updated_at=now,
            )
            logger.warning("Runtime revision drift for deploy=%s expected=%s observed=%s", locked.pk, expected_revision, observed_revision)
            return

        current_policies = runtime_policies()
        if locked.status == "running":
            from deploy.base_images import deployment_phase_remaining_seconds
            remaining = deployment_phase_remaining_seconds(locked, now=now)
            if remaining is not None and remaining <= 0:
                mark_deploy_timeout(
                    deploy=locked,
                    container_exists=bool(state),
                    container_running=running,
                )
                return
        if locked.status == DeploymentStatusChoices.PENDING and running:
            StateManager.transition_deploy(
                locked.pk,
                DeploymentStatusChoices.RUNNING,
                update_fields={
                    "stage": "running",
                    "progress": max(locked.progress, 85),
                    "status_message": "Swarm service has a running task.",
                },
            )
            return
        if locked.status == DeploymentStatusChoices.RUNNING and not running:
            stage = (locked.stage or "").strip().lower()
            if stage in PRE_CONTAINER_STAGES or int(locked.progress or 0) < 85:
                return
            if not _swarm_has_terminal_runtime_failure(state):
                logger.warning(
                    "Swarm service %s has no running task during a restart/update; "
                    "waiting for Swarm to converge.",
                    service_name,
                )
                return
            mark_deploy_failed(
                deploy=locked,
                message="The Swarm service has no running task and no active restart attempt remains.",
                stage="swarm_service_not_running",
                details=_swarm_failure_details(runtime, service_name, state),
            )
            return
        if locked.status == DeploymentStatusChoices.ROLLING_BACK:
            if running:
                mark_rollback_complete(locked)
            else:
                mark_rollback_failed(locked)

def _reconcile_desired_state(service: Service) -> bool:
    """Drive observed runtime toward Service.desired_state."""
    if swarm_enabled() and _service_has_active_native_deployment(service):
        # A native deployment owns runtime mutation until it commits a terminal
        # state. Never queue a stop/start reconciliation from a stale Service
        # projection while that deployment is applying its revision.
        logger.debug(
            "Skipping desired-state reconciliation for service %s while deployment owns runtime.",
            service.pk,
        )
        return False
    if swarm_enabled():
        runtime = SwarmRuntime()
        try:
            state = runtime.inspect_service(service.get_docker_service_name())
            running = bool(state and state.replicas_running == 1)
        except Exception as exc:
            logger.warning("Swarm desired-state inspection failed for service %s: %s", service.pk, exc)
            return False
        desired = str(getattr(service, "desired_state", "stopped") or "stopped").lower()
        if desired == "stopped":
            if not running:
                return False
            if service.status != SERVICE_STATUS_CHOICES.STOPPING:
                try:
                    from deployments.celery.tasks import stop as stop_service
                    stop_service.delay(str(service.pk))
                    return True
                except Exception:
                    logger.exception("Could not queue Swarm stop reconciliation for service %s", service.pk)
            return False
        if desired == "running" and not running and service.status not in ACTIVE_SERVICE_STATUSES:
            revision_deploy = get_authoritative_deploy(service)
            if revision_deploy and revision_deploy.status in {
                DeploymentStatusChoices.SUCCEEDED,
                DeploymentStatusChoices.FAILED,
                DeploymentStatusChoices.CANCELLED,
            }:
                try:
                    from deployments.celery.tasks import deploy as deploy_task
                    StateManager.transition_service(
                        service.pk,
                        SERVICE_STATUS_CHOICES.QUEUED,
                        update_fields={"deploy_started": timezone.now()},
                    )
                    deploy_task.delay(str(revision_deploy.pk))
                    return True
                except Exception:
                    logger.exception("Could not queue Swarm desired-state deployment for service %s", service.pk)
        return False

    desired = str(getattr(service, "desired_state", "stopped") or "stopped").lower()
    container_name = service.get_docker_service_name()
    container = Container(container_name)
    try:
        runtime = container.inspect_runtime()
        running = bool(runtime.get("running"))
    except Exception as exc:
        logger.warning("Desired-state inspection failed for service %s: %s", service.pk, exc)
        return False

    if desired == "stopped":
        if not running:
            return False
        if service.status != SERVICE_STATUS_CHOICES.STOPPING:
            try:
                from deployments.celery.tasks import stop as stop_service
                stop_service.delay(str(service.pk))
                logger.info("Queued stop reconciliation for service %s.", service.pk)
                return True
            except Exception:
                logger.exception("Could not queue stop reconciliation for service %s.", service.pk)
        return False

    if desired == "running":
        if running or service.status in ACTIVE_SERVICE_STATUSES:
            return False
        revision_deploy = get_active_deploy(service)
        if revision_deploy is None:
            return False
        if revision_deploy.status not in {
            DeploymentStatusChoices.SUCCEEDED,
            DeploymentStatusChoices.FAILED,
            DeploymentStatusChoices.CANCELLED,
        }:
            return False
        try:
            from deployments.celery.tasks import deploy as deploy_task
            StateManager.transition_service(
                service.pk,
                SERVICE_STATUS_CHOICES.QUEUED,
                update_fields={"deploy_started": timezone.now()},
            )
            deploy_task.delay(str(revision_deploy.pk))
            logger.info(
                "Queued desired-state deployment for service %s from revision %s.",
                service.pk,
                revision_deploy.revision_id,
            )
            return True
        except Exception:
            logger.exception("Could not queue desired-state deployment for service %s", service.pk)
    return False


def _reconcile_service_runtime(service: Service) -> None:
    if swarm_enabled():
        _reconcile_service_runtime_swarm(service)
        return
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
    deploy = get_active_deploy(service)

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

        # Resolve the active revision separately; selected_deploy is only a
        # legacy fallback inside get_active_deploy().
        deploy = get_active_deploy(locked)

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


def _native_reconciliation_plan(
    service: Service,
    deploy: Deploy | None,
    selection,
):
    if deploy is None or not getattr(deploy, "revision_id", None):
        return None
    release = getattr(deploy, "release_reference", None)
    if release is None:
        try:
            from deploy.models import Release
            release = (
                Release.objects
                .filter(
                    service_id=service.pk,
                    revision_id=deploy.revision_id,
                    status="promoted",
                )
                .select_related("artifact", "revision")
                .order_by("-promoted_at", "-created_at")
                .first()
            )
        except Exception:
            release = None
    revision = getattr(service, "active_revision", None) or getattr(deploy, "revision", None)
    if revision is None:
        return None
    graph = __import__("deployments.core.runtime_graph", fromlist=["ServiceRuntimeGraph"]).ServiceRuntimeGraph.from_revision(revision)
    config = materialize_revision_config(revision)
    runtime_options = dict(config.get("runtime_options") or {})
    resolved = ConfigurationResolver().resolve(
        platform_policy={
            "resource_limits": runtime_limits(getattr(service, "plan", None)),
            "max_replicas": int(getattr(getattr(service, "plan", None), "max_replicas", 8) or 8),
        },
        revision_snapshot={
            "environment": dict(config.get("environment") or config.get("env") or {}),
            "runtime_options": runtime_options,
            "networks": list(getattr(graph, "networks", ()) or ()),
            "volumes": list(getattr(graph, "volumes", ()) or ()),
            "endpoints": [
                {
                    "name": endpoint.name,
                    "target_port": endpoint.target_port,
                    "published_port": endpoint.published_port,
                    "protocol": endpoint.protocol,
                    "exposure": endpoint.exposure,
                    "hostname": endpoint.hostname,
                    "path": endpoint.path,
                    "tls": endpoint.tls,
                    "enabled": endpoint.enabled,
                    "process": endpoint.process,
                    "metadata": dict(endpoint.metadata),
                }
                for endpoint in (getattr(graph, "endpoints", ()) or ())
            ],
            "health_policy": dict(
                config.get("health_policy")
                or runtime_options.get("healthcheck")
                or {}
            ),
            "rollout_policy": dict(config.get("rollout_policy") or {}),
            "release_spec": dict(config.get("release_spec") or (getattr(release, "release_command", {}) or {})),
            "labels": dict(config.get("labels") or {}),
        },
    )
    identity = RuntimeIdentity(
        service_id=str(service.pk),
        deployment_id=str(getattr(deploy, "pk", "") or "") or None,
        revision_id=str(getattr(revision, "pk", "") or "") or None,
        process_name="web",
        runtime_name=service.get_docker_service_name(),
    )
    image_ref = (
        str(getattr(getattr(release, "artifact", None), "image_ref", "") or "")
        or str(getattr(deploy, "image_ref", "") or "")
    )
    if not image_ref:
        return None
    plan = DeploymentPlanCompiler().compile(
        identity=identity,
        graph=graph,
        selection=selection,
        resolved=resolved,
        image_ref=image_ref,
    )
    return __import__("dataclasses").replace(
        plan,
        artifact_digest=str(getattr(getattr(release, "artifact", None), "digest", "") or getattr(deploy, "image_digest", "") or ""),
        release_id=str(getattr(release, "pk", "") or "") or None,
        release_spec=dict(getattr(release, "release_command", {}) or plan.release_spec),
        rollout_policy=dict(getattr(release, "rollout_policy", {}) or plan.rollout_policy),
        health_policy=dict(getattr(release, "health_policy", {}) or plan.health_policy),
    )


def _service_has_active_native_deployment(service: Service) -> bool:
    """Return whether an active deployment worker currently owns runtime mutation."""
    return Deploy.objects.filter(
        service_id=service.pk,
        status__in=ACTIVE_DEPLOY_STATUSES,
        cancel_requested=False,
    ).exists()


def _reconcile_service_runtime_swarm(service: Service) -> None:
    # DeploymentLifecycleExecutor owns runtime mutation while an attempt is
    # active. The service-level reconciler must not invent a second plan from
    # the pre-activation state (active_revision can still point to the previous
    # release or be empty).
    if _service_has_active_native_deployment(service):
        logger.debug(
            "Skipping service runtime reconciliation for %s while an active deployment owns the runtime.",
            service.pk,
        )
        return

    resolver = DjangoRuntimeSelectionResolver()
    selection = resolver.resolve(
        service=service,
        revision=getattr(service, "active_revision", None),
        deployment=get_authoritative_deploy(service),
        probe=True,
    )
    runtime = resolver.registry.resolve_adapter(selection)
    service_name = service.get_docker_service_name()
    deploy = get_authoritative_deploy(service)

    try:
        observed = runtime.inspect(
            RuntimeIdentity(
                service_id=str(service.pk),
                deployment_id=str(getattr(deploy, "pk", "") or "") or None,
                revision_id=str(getattr(getattr(service, "active_revision", None), "pk", "") or "") or None,
                process_name="web",
                runtime_name=service_name,
            )
        )
    except Exception as exc:
        logger.warning("Swarm runtime observation failed for service %s: %s", service.pk, exc)
        return

    desired_state = str(getattr(service, "desired_state", "") or "").lower()
    if desired_state not in {"running", "stopped"}:
        desired_state = (
            "stopped"
            if service.status in {SERVICE_STATUS_CHOICES.STOPPING, SERVICE_STATUS_CHOICES.STOPPED}
            else "running"
        )
    desired = DesiredRuntimeState(
        service_id=str(service.pk),
        revision_id=str(getattr(getattr(service, "active_revision", None), "pk", "") or "") or None,
        desired_state=desired_state,
        runtime_name=service_name,
        metadata={
            "readiness_timeout": int(runtime_policies().get("queued_timeout_minutes", 10) or 10) * 60,
        },
    )
    plan = None
    try:
        if desired_state == "running" and deploy is not None:
            plan = _native_reconciliation_plan(service, deploy, selection)
    except Exception:
        logger.exception("Could not construct native reconciliation plan for service %s", service.pk)
        return

    if plan is not None:
        desired = __import__("dataclasses").replace(
            desired,
            required_capabilities=plan.required_capabilities,
        )
    elif desired_state == "running" and observed.status.value != "missing":
        # An existing runtime without a reconstructable native plan is not
        # safely actionable. Treat it as manual intervention instead of
        # reaching ReconciliationExecutor with an invalid None plan.
        logger.warning(
            "Skipping Swarm runtime reconciliation for service=%s: no native DeploymentPlan could be reconstructed.",
            service.pk,
        )
        return

    decision = ReconciliationPlanner().decide(desired, observed, selection)
    logger.info(
        "Swarm reconciliation decision service=%s action=%s reason=%s",
        service.pk,
        decision.action.value,
        decision.reason_code,
    )

    if decision.action in {
        ReconciliationAction.CONVERGED,
        ReconciliationAction.BLOCKED,
        ReconciliationAction.MANUAL_INTERVENTION,
    }:
        if decision.action is ReconciliationAction.BLOCKED:
            logger.warning(
                "Swarm reconciliation blocked service=%s reason=%s details=%s",
                service.pk, decision.reason_code, decision.details,
            )
        with transaction.atomic():
            locked = Service.objects.select_for_update().filter(pk=service.pk).first()
            if not locked:
                return
            if (
                decision.action is ReconciliationAction.CONVERGED
                and locked.status == SERVICE_STATUS_CHOICES.SUCCEEDED
            ):
                mark_service_running(locked, deploy=get_authoritative_deploy(locked))
        return

    generation = getattr(service, "lifecycle_generation", 0)
    context = ReconciliationExecutionContext(
        service_id=str(service.pk),
        lifecycle_generation=generation,
        active_revision_id=desired.revision_id,
        owns_execution=lambda sid=str(service.pk), gen=generation: (
            Service.objects.filter(
                pk=sid, lifecycle_generation=gen,
            ).exists()
            and not Deploy.objects.filter(
                service_id=sid,
                status__in=ACTIVE_DEPLOY_STATUSES,
                cancel_requested=False,
            ).exists()
        ),
        current_generation=lambda sid=str(service.pk): Service.objects.filter(
            pk=sid
        ).values_list("lifecycle_generation", flat=True).first(),
        cancellation_requested=lambda sid=str(service.pk): (
            str(Service.objects.filter(pk=sid).values_list("desired_state", flat=True).first() or "").lower()
            != "running"
            if desired_state == "running"
            else False
        ),
    )

    handle = None
    if decision.action is ReconciliationAction.STOP:
        handle = RuntimeHandle(
            backend=selection.backend,
            identity=observed.identity,
            runtime_id=observed.runtime_id,
            resource_name=observed.identity.resource_name(),
        )
    try:
        result = ReconciliationExecutor().execute(
            decision,
            desired=desired,
            selection=selection,
            runtime=runtime,
            context=context,
            plan=plan,
            handle=handle,
        )
    except Exception as exc:
        logger.exception(
            "Swarm reconciliation execution failed service=%s action=%s reason=%s",
            service.pk, decision.action.value, decision.reason_code,
        )
        return

    if result is None:
        return
    with transaction.atomic():
        locked = Service.objects.select_for_update().filter(pk=service.pk).first()
        if not locked:
            return
        if decision.action is ReconciliationAction.STOP:
            mark_service_stopped(locked, deploy=get_authoritative_deploy(locked))
        elif result.success and decision.action in {
            ReconciliationAction.CREATE,
            ReconciliationAction.UPDATE,
            ReconciliationAction.REPAIR,
        }:
            mark_service_running(locked, deploy=get_authoritative_deploy(locked))



# ---- (removed old handlers, replaced by monitoring.actions) ----


def _reconcile_base_runtime_builds(policies: dict) -> None:
    """Recover base-image rows whose builder disappeared or exceeded the operator timeout."""
    cutoff = timezone.now() - timedelta(
        minutes=int(policies["base_image_build_timeout_minutes"])
    )
    stale = BaseRuntimeImage.objects.filter(
        status=BaseRuntimeImage.Status.BUILDING,
        build_started_at__lt=cutoff,
    ).order_by("build_started_at")[: int(policies["monitor_batch_size"])]
    for row in stale:
        try:
            # retry_pending is still part of the same bounded base-image phase.
            # Once the deadline is exceeded, the build owner must be fenced
            # and waiters must be released rather than waiting indefinitely.
            updated = BaseRuntimeImage.objects.filter(
                pk=row.pk,
                status=BaseRuntimeImage.Status.BUILDING,
                build_started_at__lt=cutoff,
                build_task_id=row.build_task_id,
            ).update(
                status=BaseRuntimeImage.Status.FAILED,
                build_task_id="",
                build_owner_deployment_id="",
                last_error="Base image build exceeded its operator-owned lifecycle timeout.",
                last_error_details={
                    "stage": "base_image",
                    "exception_type": "BaseImageTimeout",
                    "technical_message": "Base image build exceeded its operator-owned lifecycle timeout.",
                    "retry_pending": False,
                    "base_image_ref": row.image_ref,
                    "resource_policy_source": "server_owned",
                    "docker_api_reached": None,
                },
                build_completed_at=timezone.now(),
                updated_at=timezone.now(),
            )
            if updated and policies["recovery_enabled"]:
                # A later deployment/admin rebuild can safely claim the row again.
                logger.warning("Recovered stale base-image build row %s (%s)", row.pk, row.image_ref)
        except Exception:
            logger.exception("Failed to reconcile stale base-image row %s", row.pk)
