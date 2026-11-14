from __future__ import annotations

import logging
import uuid
from celery import shared_task
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from deployments.celery.tasks import deploy as deploy_task, run_db_deploy, stop as stop_service_task
from deployments.core.db_deployer import DB_PLATFORMS
from core.global_settings.config import SERVICE_STATUS_CHOICES
from services.models import Service
from services.lifecycle import bump_lifecycle
from deployments.common.exceptions import to_deployment_error
from deploy.models import DeploymentStatusChoices
from .models import ApplicationInstance, ApplicationInstanceService, ApplicationStatus
from .executor import ApplicationStackExecutor

logger = logging.getLogger(__name__)


def _mark_instance_failed(instance_id, message: str, code: str = "APPLICATION_DEPLOYMENT_FAILED"):
    with transaction.atomic():
        instance = ApplicationInstance.objects.select_for_update().filter(pk=instance_id).first()
        if not instance or instance.status != ApplicationStatus.DEPLOYING or instance.cancel_requested:
            return False
        instance.status = ApplicationStatus.FAILED
        instance.stage = "service_failed"
        instance.error_code = code
        instance.error_message = message
        instance.save(update_fields=["status", "stage", "error_code", "error_message", "updated_at"])
        return True


def _schedule_next(
    instance_id: str,
    current_key: str | None = None,
    runtime_operation_generation: int | None = None,
):
    """Reconcile the immutable application DAG and dispatch its ready frontier."""
    executor = ApplicationStackExecutor(instance_id)
    dispatches = executor.reconcile()
    for dispatch in dispatches:
        try:
            callback_args = (
                dispatch.instance_id,
                dispatch.service_key,
                dispatch.task_id,
            )
            if runtime_operation_generation is None:
                callback = advance_application_service.si(*callback_args)
                failure = application_service_failed.si(*callback_args)
            else:
                callback = advance_application_service.si(
                    *callback_args, int(runtime_operation_generation)
                )
                failure = application_service_failed.si(
                    *callback_args, int(runtime_operation_generation)
                )
            # Database services have a dedicated deployment worker.
            # Dispatch them directly so the application callback/errback stays
            # attached to the actual execution task instead of being lost by
            # the generic deploy wrapper. The platform is captured by the
            # locked coordinator dispatch, so the scheduler does not need a
            # second database lookup for every child.
            platform = str(getattr(dispatch, "platform", "") or "").strip().lower()
            task = run_db_deploy if platform in DB_PLATFORMS else deploy_task
            task.apply_async(
                args=[str(dispatch.deploy_id)],
                link=callback,
                link_error=failure,
                task_id=dispatch.task_id,
                queue="deployments",
            )
            logger.info(
                "Dispatched application child service %s/%s deploy=%s task=%s",
                dispatch.instance_id,
                dispatch.service_key,
                dispatch.deploy_id,
                dispatch.task_id,
            )
        except Exception:
            logger.exception(
                "Unable to queue application child service %s/%s deploy=%s",
                dispatch.instance_id,
                dispatch.service_key,
                dispatch.deploy_id,
            )
            # Clear the dispatch claim so the periodic reconciler can safely
            # retry this service without creating a duplicate task.
            ApplicationInstanceService.objects.filter(
                pk=dispatch.binding_id,
                dispatched_at__isnull=False,
            ).update(dispatched_at=None, dispatch_task_id="")



@shared_task(bind=True, name="app_catalog.start_application_installation")
def start_application_installation(self, instance_id: str):
    try:
        executor = ApplicationStackExecutor(instance_id)
        claimed = executor.start(task_id=str(self.request.id))
        if claimed:
            _schedule_next(str(instance_id))
    except Exception as exc:
        logger.exception("Application installation start failed for %s", instance_id)
        instance = ApplicationInstance.objects.filter(pk=instance_id).first()
        if instance:
            error = to_deployment_error(exc, stage="application_orchestration")
            _mark_instance_failed(instance_id, error.user_message, error.code)


@shared_task(bind=True, name="app_catalog.gate_application_service")
def gate_application_service(self, instance_id: str, service_key: str):
    with transaction.atomic():
        instance = ApplicationInstance.objects.select_for_update().filter(pk=instance_id).first()
        binding = (ApplicationInstanceService.objects.select_for_update()
                   .select_related("deploy", "service__plan", "instance")
                   .filter(instance_id=instance_id, service_key=service_key).first())
        if not instance or not binding:
            return
        if instance.status != ApplicationStatus.DEPLOYING or instance.cancel_requested:
            binding.dispatched_at = None
            binding.dispatch_task_id = ""
            binding.save(update_fields=["dispatched_at", "dispatch_task_id"])
            return
        if binding.dispatch_task_id != str(self.request.id):
            return
        try:
            _loaded_instance, plan = ApplicationStackExecutor(instance_id)._load()
            service_spec = plan.service(service_key)
            deps = list(service_spec.dependencies or ())
            dependency_statuses = {
                dep: instance.services.filter(service_key=dep).values_list("deploy__status", flat=True).first()
                for dep in deps
            }
            failed = [dep for dep, st in dependency_statuses.items() if st in {DeploymentStatusChoices.FAILED, DeploymentStatusChoices.ROLLED_BACK, DeploymentStatusChoices.CANCELLED}]
            if failed:
                binding.dispatched_at = None
                binding.dispatch_task_id = ""
                binding.save(update_fields=["dispatched_at", "dispatch_task_id"])
                _mark_instance_failed(instance_id, "Required service(s) did not deploy successfully: " + ", ".join(sorted(failed)) + ".", "APPLICATION_DEPENDENCY_FAILED")
                return
            if any(st != DeploymentStatusChoices.SUCCEEDED for st in dependency_statuses.values()):
                binding.dispatched_at = None
                binding.dispatch_task_id = ""
                binding.save(update_fields=["dispatched_at", "dispatch_task_id"])
                return
            child_task_id = str(uuid.uuid4())
            binding.dispatch_task_id = child_task_id
            binding.dispatched_at = timezone.now()
            binding.save(update_fields=["dispatch_task_id", "dispatched_at"])
            callback = advance_application_service.si(instance_id, service_key, child_task_id)
            failure = application_service_failed.si(instance_id, service_key, child_task_id)
            platform = str(
                getattr(getattr(binding.service, "plan", None), "platform", "") or ""
            ).strip().lower()
            child_task = run_db_deploy if platform in DB_PLATFORMS else deploy_task
            transaction.on_commit(
                lambda: child_task.apply_async(
                    args=[str(binding.deploy_id)],
                    link=callback,
                    link_error=failure,
                    task_id=child_task_id,
                    queue="deployments",
                )
            )
        except Exception as exc:
            logger.exception("Application service gate failed for %s/%s", instance_id, service_key)
            binding.dispatched_at = None
            binding.dispatch_task_id = ""
            binding.save(update_fields=["dispatched_at", "dispatch_task_id"])
            _mark_instance_failed(instance_id, f"{service_key}: {to_deployment_error(exc, stage='application_orchestration').user_message}", "APPLICATION_PLAN_INVALID")


@shared_task(name="app_catalog.advance_application_service")
def advance_application_service(
    instance_id: str,
    service_key: str,
    child_task_id: str | None = None,
    runtime_operation_generation: int | None = None,
):
    with transaction.atomic():
        if runtime_operation_generation is not None:
            owner = ApplicationInstance.objects.select_for_update().filter(pk=instance_id).first()
            if (
                owner is None
                or owner.status != ApplicationStatus.DEPLOYING
                or owner.runtime_operation != "start"
                or int(owner.runtime_operation_generation or 0) != int(runtime_operation_generation)
            ):
                return
        binding = ApplicationInstanceService.objects.select_for_update().filter(instance_id=instance_id, service_key=service_key).first()
        if not binding or (child_task_id and binding.dispatch_task_id != child_task_id):
            return
        binding.dispatched_at = None
        binding.dispatch_task_id = ""
        binding.save(update_fields=["dispatched_at", "dispatch_task_id"])
    _schedule_next(
        instance_id,
        current_key=service_key,
        runtime_operation_generation=runtime_operation_generation,
    )


@shared_task(name="app_catalog.application_service_failed")
def application_service_failed(
    instance_id: str,
    service_key: str,
    child_task_id: str | None = None,
    runtime_operation_generation: int | None = None,
    *args,
    **kwargs,
):
    with transaction.atomic():
        if runtime_operation_generation is not None:
            owner = ApplicationInstance.objects.select_for_update().filter(pk=instance_id).first()
            if (
                owner is None
                or owner.status != ApplicationStatus.DEPLOYING
                or owner.runtime_operation != "start"
                or int(owner.runtime_operation_generation or 0) != int(runtime_operation_generation)
            ):
                return
        binding = ApplicationInstanceService.objects.select_for_update().filter(instance_id=instance_id, service_key=service_key).first()
        if not binding or (child_task_id and binding.dispatch_task_id != child_task_id):
            return
        binding.dispatched_at = None
        binding.dispatch_task_id = ""
        binding.save(update_fields=["dispatched_at", "dispatch_task_id"])
    _schedule_next(
        instance_id,
        current_key=service_key,
        runtime_operation_generation=runtime_operation_generation,
    )


@shared_task(bind=True, name="app_catalog.start_application_runtime")
def start_application_runtime(self, instance_id: str, runtime_operation_generation: int):
    """Resume Start All using the existing dependency-aware install scheduler."""
    owner = ApplicationInstance.objects.filter(
        pk=instance_id,
        status=ApplicationStatus.DEPLOYING,
        runtime_operation="start",
        runtime_operation_generation=int(runtime_operation_generation),
        stage="starting_services",
    ).first()
    if owner is None:
        return {"started": False, "reason": "stale_operation"}
    _schedule_next(
        str(instance_id),
        runtime_operation_generation=int(runtime_operation_generation),
    )
    return {"started": True}


def _finish_application_stop(
    instance_id: str,
    runtime_operation_generation: int,
    *,
    failed_service_key: str | None = None,
    message: str = "",
) -> bool:
    with transaction.atomic():
        owner = ApplicationInstance.objects.select_for_update().filter(pk=instance_id).first()
        if (
            owner is None
            or owner.status != ApplicationStatus.STOPPING
            or owner.runtime_operation != "stop"
            or int(owner.runtime_operation_generation or 0) != int(runtime_operation_generation)
        ):
            return False
        if failed_service_key:
            owner.status = ApplicationStatus.DEGRADED
            owner.stage = "runtime_stop_failed"
            owner.error_code = "APPLICATION_RUNTIME_STOP_FAILED"
            owner.error_message = message or (
                f"Could not confirm that application service '{failed_service_key}' stopped. "
                "Its dependencies were left running."
            )
        else:
            owner.status = ApplicationStatus.STOPPED
            owner.stage = "application_stopped"
            owner.error_code = ""
            owner.error_message = ""
        owner.runtime_operation = ""
        owner.save(update_fields=[
            "status", "stage", "runtime_operation", "error_code",
            "error_message", "updated_at",
        ])
        if failed_service_key and failed_service_key != "application":
            failed_service_id = (
                ApplicationInstanceService.objects
                .filter(instance_id=owner.pk, service_key=failed_service_key)
                .values_list("service_id", flat=True)
                .first()
            )
            if failed_service_id:
                Service.objects.filter(
                    pk=failed_service_id,
                    status=SERVICE_STATUS_CHOICES.STOPPING,
                    desired_state="stopped",
                ).update(deploy_started=None)
        return True


def _continue_application_stop(
    instance_id: str,
    runtime_operation_generation: int,
) -> dict[str, object]:
    """Stop one service at a time in reverse dependency order."""
    try:
        _instance, plan = ApplicationStackExecutor(str(instance_id))._load()
        stop_order = tuple(reversed(plan.topological_order()))
    except Exception as exc:
        _finish_application_stop(
            str(instance_id),
            int(runtime_operation_generation),
            failed_service_key="application",
            message=f"Application dependency graph could not be loaded for Stop All: {exc}",
        )
        return {"stopped": False, "reason": "invalid_graph"}

    stale_seconds = 300
    try:
        from django.conf import settings
        stale_seconds = max(60, int(getattr(settings, "CATALOG_DISPATCH_STALE_SECONDS", 300)))
    except Exception:
        pass

    for service_key in stop_order:
        task_data = None
        with transaction.atomic():
            owner = ApplicationInstance.objects.select_for_update().filter(pk=instance_id).first()
            if (
                owner is None
                or owner.stage == "deletion_pending"
                or owner.status != ApplicationStatus.STOPPING
                or owner.runtime_operation != "stop"
                or int(owner.runtime_operation_generation or 0) != int(runtime_operation_generation)
            ):
                return {"stopped": False, "reason": "stale_operation"}

            binding = (
                ApplicationInstanceService.objects.select_for_update()
                .filter(instance_id=instance_id, service_key=service_key)
                .first()
            )
            if binding is None:
                task_data = {"failed": True, "message": f"Application service binding '{service_key}' is missing."}
            else:
                service = Service.objects.select_for_update().filter(pk=binding.service_id).first()
                if service is None:
                    task_data = {"failed": True, "message": f"Application service '{service_key}' no longer exists."}
                else:
                    service_status = str(service.status or "").lower()
                    desired_state = str(service.desired_state or "").lower()
                    stopped_status = str(SERVICE_STATUS_CHOICES.STOPPED).lower()
                    stopping_status = str(SERVICE_STATUS_CHOICES.STOPPING).lower()
                    if service_status == stopped_status:
                        if desired_state != "stopped":
                            lifecycle_generation = bump_lifecycle(
                                service.pk,
                                desired_state="stopped",
                            )
                            service.desired_state = "stopped"
                            service.lifecycle_generation = lifecycle_generation
                            service.save(update_fields=["desired_state", "lifecycle_generation"])
                        continue
                    if service_status in {
                        str(SERVICE_STATUS_CHOICES.QUEUED).lower(),
                        str(SERVICE_STATUS_CHOICES.DEPLOYING).lower(),
                    }:
                        task_data = {
                            "failed": True,
                            "message": (
                                f"Cannot safely continue Stop All because dependent service '{service_key}' "
                                f"is still {service_status}."
                            ),
                        }
                    else:
                        now = timezone.now()
                        already_stopping = service_status == stopping_status and desired_state == "stopped"
                        if already_stopping:
                            age = (
                                (now - service.deploy_started).total_seconds()
                                if service.deploy_started else stale_seconds + 1
                            )
                            if age < stale_seconds:
                                return {
                                    "stopped": False,
                                    "reason": "child_stop_in_progress",
                                    "service": service_key,
                                }
                            lifecycle_generation = int(service.lifecycle_generation or 0)
                            task_id = str(service.task_id or uuid.uuid4())
                        else:
                            lifecycle_generation = bump_lifecycle(service.pk, desired_state="stopped")
                            task_id = str(uuid.uuid4())
                            service.status = SERVICE_STATUS_CHOICES.STOPPING
                            service.desired_state = "stopped"
                            service.lifecycle_generation = lifecycle_generation
                            service.task_id = task_id
                            service.deploy_started = now
                            service.save(update_fields=[
                                "status", "desired_state", "lifecycle_generation",
                                "task_id", "deploy_started",
                            ])
                        task_data = {
                            "service_id": str(service.pk),
                            "service_key": service_key,
                            "lifecycle_generation": lifecycle_generation,
                            "task_id": task_id,
                        }

        if task_data and task_data.get("failed"):
            _finish_application_stop(
                str(instance_id),
                int(runtime_operation_generation),
                failed_service_key=service_key,
                message=str(task_data.get("message") or ""),
            )
            return {"stopped": False, "reason": "child_stop_precondition_failed"}

        if task_data:
            try:
                stop_service_task.apply_async(
                    args=[task_data["service_id"]],
                    kwargs={
                        "expected_lifecycle_generation": task_data["lifecycle_generation"],
                    },
                    task_id=task_data["task_id"],
                    link=advance_application_stop.si(
                        str(instance_id), service_key, int(runtime_operation_generation)
                    ),
                    link_error=application_stop_failed.si(
                        str(instance_id), service_key, int(runtime_operation_generation)
                    ),
                    queue="deployments",
                )
            except Exception:
                logger.exception(
                    "Unable to queue Stop All child service %s/%s",
                    instance_id,
                    service_key,
                )
                Service.objects.filter(
                    pk=task_data["service_id"],
                    lifecycle_generation=task_data["lifecycle_generation"],
                    task_id=task_data["task_id"],
                ).update(deploy_started=None)
            return {
                "stopped": False,
                "dispatched": service_key,
                "task_id": task_data["task_id"],
            }

    _finish_application_stop(str(instance_id), int(runtime_operation_generation))
    return {"stopped": True}


@shared_task(bind=True, name="app_catalog.stop_application_runtime")
def stop_application_runtime(self, instance_id: str, runtime_operation_generation: int):
    """Begin or resume the reverse dependency-order Stop All coordinator."""
    return _continue_application_stop(
        str(instance_id),
        int(runtime_operation_generation),
    )


@shared_task(name="app_catalog.advance_application_stop")
def advance_application_stop(
    instance_id: str,
    service_key: str,
    runtime_operation_generation: int,
):
    owner = ApplicationInstance.objects.filter(
        pk=instance_id,
        status=ApplicationStatus.STOPPING,
        runtime_operation="stop",
        runtime_operation_generation=int(runtime_operation_generation),
    ).first()
    if owner is None:
        return {"advanced": False, "reason": "stale_operation"}

    binding = ApplicationInstanceService.objects.select_related("service").filter(
        instance_id=instance_id,
        service_key=service_key,
    ).first()
    if (
        binding is None
        or str(binding.service.status or "").lower() != str(SERVICE_STATUS_CHOICES.STOPPED).lower()
        or str(binding.service.desired_state or "").lower() != "stopped"
    ):
        _finish_application_stop(
            str(instance_id),
            int(runtime_operation_generation),
            failed_service_key=service_key,
        )
        return {"advanced": False, "reason": "stop_not_confirmed"}

    return _continue_application_stop(
        str(instance_id),
        int(runtime_operation_generation),
    )


@shared_task(name="app_catalog.application_stop_failed")
def application_stop_failed(
    instance_id: str,
    service_key: str,
    runtime_operation_generation: int,
    *args,
    **kwargs,
):
    _finish_application_stop(
        str(instance_id),
        int(runtime_operation_generation),
        failed_service_key=service_key,
    )
    logger.error(
        "Ready App Stop All stopped at service %s/%s; dependency services remain running.",
        instance_id,
        service_key,
    )


@shared_task(name="app_catalog.supervise_ready_applications")
def supervise_ready_applications():
    """Continuously validate RUNNING Ready App coordinator state.

    Runtime Docker/Swarm repair remains owned by the deployment monitor. This
    task makes sure a healthy-looking application row cannot remain stale when
    child state, ownership metadata, or the application network drift.
    """
    batch_size = 100
    try:
        from django.conf import settings
        batch_size = max(
            1,
            int(getattr(settings, "CATALOG_RUNTIME_SUPERVISOR_BATCH_SIZE", 100)),
        )
    except (TypeError, ValueError):
        pass

    queryset = (
        ApplicationInstance.objects
        .filter(
            Q(
                status__in=(
                    ApplicationStatus.RUNNING,
                    ApplicationStatus.DEGRADED,
                    ApplicationStatus.STOPPED,
                ),
            )
            | Q(
                status=ApplicationStatus.FAILED,
                stage="state_corrupted",
                error_code="APPLICATION_STATE_CORRUPTED",
            )
        )
        .exclude(stage="deletion_pending")
        .order_by("updated_at")
    )[:batch_size]

    healthy = degraded = stopped = corrupted = missing = unavailable = 0
    for instance in queryset.iterator():
        try:
            result = ApplicationStackExecutor(str(instance.pk)).supervise_runtime()
            state = str(result.get("status") or "")
            if state == "healthy":
                healthy += 1
            elif state == "degraded":
                degraded += 1
            elif state == "stopped":
                stopped += 1
            elif state == "corrupted":
                corrupted += 1
            elif state == "missing":
                missing += 1
            elif state == "database_unavailable":
                unavailable += 1
        except Exception:
            logger.exception(
                "Ready App runtime supervisor failed for application %s",
                instance.pk,
            )

    return {
        "status": "ok",
        "checked": healthy + degraded + stopped + corrupted + missing + unavailable,
        "healthy": healthy,
        "degraded": degraded,
        "stopped": stopped,
        "corrupted": corrupted,
        "missing": missing,
        "database_unavailable": unavailable,
    }


@shared_task(
    bind=True,
    name="app_catalog.cancel_application_installation",
    max_retries=None,
)
def cancel_application_installation(
    self,
    instance_id: str,
    reason: str = "Application deployment cancelled by user request.",
):
    """Converge Ready App cancellation until all child runtime is gone."""
    executor = ApplicationStackExecutor(instance_id)
    try:
        instance = ApplicationInstance.objects.filter(pk=instance_id).first()
        if instance is None:
            return {"cancelled": True, "reason": "already_absent"}
        if instance.stage == "deletion_pending":
            return {"cancelled": False, "reason": "deletion_in_progress"}

        executor.cancel(reason=reason)
        if executor._cleanup_cancelled_children():
            return {"cancelled": True}
        return self.retry(countdown=10)
    except ApplicationInstance.DoesNotExist:
        return {"cancelled": True, "reason": "already_absent"}
    except Exception as exc:
        logger.exception("Ready App cancellation convergence failed for %s", instance_id)
        try:
            ApplicationInstance.objects.filter(pk=instance_id).exclude(
                stage="deletion_pending"
            ).update(
                stage="cancellation_cleanup",
                error_code="APPLICATION_DEPLOYMENT_CANCELLED",
                error_message="Application cancellation is still stopping child runtime resources.",
                updated_at=timezone.now(),
            )
        except Exception:
            logger.exception("Unable to persist cancellation-cleanup state for %s", instance_id)
        raise self.retry(exc=exc, countdown=10)


@shared_task(
    bind=True,
    name="app_catalog.delete_application_installation",
    max_retries=None,
)
def delete_application_installation(self, instance_id: str):
    """Retry Ready App deletion until all owned resources converge."""
    instance = ApplicationInstance.objects.filter(pk=instance_id).first()
    if instance is None:
        return {"deleted": True, "reason": "already_absent"}

    try:
        deleted = ApplicationStackExecutor(str(instance_id)).cleanup_terminal_application()
        if deleted:
            return {"deleted": True}
        return self.retry(countdown=15)
    except ApplicationInstance.DoesNotExist:
        return {"deleted": True, "reason": "already_absent"}
    except Exception as exc:
        logger.exception("Ready App deletion retry failed for %s", instance_id)
        try:
            ApplicationInstance.objects.filter(pk=instance_id).update(
                stage="deletion_pending",
                error_code="APPLICATION_DELETION_PENDING",
                updated_at=timezone.now(),
            )
        except Exception:
            logger.exception("Unable to persist deletion-pending state for %s", instance_id)
        raise self.retry(exc=exc, countdown=15)


@shared_task(name="app_catalog.reconcile_application_installations")
def reconcile_application_installations():
    """Recover missed Celery callbacks and broker/worker interruptions.

    A service dispatch is considered stranded only when its child Deploy is
    still PENDING and its coordinator claim is older than the configured
    dispatch lease. Running child deployments are left to the deployment
    engine's own heartbeat/recovery machinery.
    """
    stale_seconds = 300
    try:
        from django.conf import settings
        stale_seconds = max(60, int(getattr(settings, "CATALOG_DISPATCH_STALE_SECONDS", 300)))
    except Exception:
        pass
    cutoff = timezone.now() - timedelta(seconds=stale_seconds)
    # Recovery applies to every non-terminal coordinator, not only
    # cancellations. A lost success/failure callback or broker interruption
    # can leave a child claim stranded while the parent remains DEPLOYING.
    instances = ApplicationInstance.objects.filter(
        status__in=(
            ApplicationStatus.PENDING,
            ApplicationStatus.DEPLOYING,
            ApplicationStatus.RUNNING,
            ApplicationStatus.STOPPING,
            ApplicationStatus.CANCELLED,
        ),
        cancel_requested__in=(False, True),
    ).only("pk")
    recovered = 0

    # Deletion intent is durable state, not a stale-cache condition. Process
    # every deletion_pending installation on every reconciliation tick so the
    # deployments worker remains a fallback executor even when the operations
    # queue is unavailable.
    pending_deletions = ApplicationInstance.objects.filter(
        stage="deletion_pending",
        status__in=(
            ApplicationStatus.PENDING,
            ApplicationStatus.DEPLOYING,
            ApplicationStatus.RUNNING,
            ApplicationStatus.STOPPING,
            ApplicationStatus.STOPPED,
            ApplicationStatus.DEGRADED,
            ApplicationStatus.FAILED,
            ApplicationStatus.CANCELLED,
        ),
    ).only("pk")
    for pending in pending_deletions.iterator():
        try:
            if ApplicationStackExecutor(str(pending.pk)).cleanup_terminal_application():
                recovered += 1
        except ApplicationInstance.DoesNotExist:
            recovered += 1
        except Exception:
            logger.exception("Ready App deletion reconciliation failed for %s", pending.pk)

    for instance in instances.iterator():
        # A cancellation task can be lost after the API commits the flag.
        # Re-apply cancellation from the periodic reconciler so child
        # deployments cannot remain active forever.
        try:
            fresh = ApplicationInstance.objects.only(
                "status", "cancel_requested", "stage"
            ).get(pk=instance.pk)
            if fresh.cancel_requested:
                executor = ApplicationStackExecutor(str(instance.pk))
                executor.cancel(
                    reason="Application deployment cancelled by user request."
                )
                try:
                    executor._cleanup_cancelled_children()
                except Exception:
                    logger.exception(
                        "Ready App cancellation cleanup still converging for %s",
                        instance.pk,
                    )
                continue
        except ApplicationInstance.DoesNotExist:
            continue

        stale = ApplicationInstanceService.objects.filter(
            instance_id=instance.pk,
            dispatched_at__lt=cutoff,
            deploy__status__in=(
                DeploymentStatusChoices.PENDING,
                DeploymentStatusChoices.SUCCEEDED,
                DeploymentStatusChoices.FAILED,
                DeploymentStatusChoices.ROLLED_BACK,
                DeploymentStatusChoices.CANCELLED,
            ),
        )
        if stale.exists():
            count = stale.count()
            stale.update(dispatched_at=None, dispatch_task_id="")
            recovered += count
        try:
            # _schedule_next() is safe only after a coordinator has actually
            # claimed execution. For an old PENDING coordinator, recover the
            # missing start task first rather than dispatching child services
            # without a coordinator owner.
            fresh = ApplicationInstance.objects.only(
                "status", "cancel_requested", "execution_task_id", "stage",
                "runtime_operation", "runtime_operation_generation",
            ).get(pk=instance.pk)
            if fresh.status == ApplicationStatus.DEPLOYING:
                runtime_generation = (
                    int(fresh.runtime_operation_generation or 0)
                    if fresh.runtime_operation == "start"
                    else None
                )
                _schedule_next(
                    str(instance.pk),
                    runtime_operation_generation=runtime_generation,
                )
            elif fresh.status == ApplicationStatus.STOPPING and fresh.runtime_operation == "stop":
                _continue_application_stop(
                    str(instance.pk),
                    int(fresh.runtime_operation_generation or 0),
                )
        except Exception:
            logger.exception("Application reconciliation failed for %s", instance.pk)


    # Recover application coordinators whose creation transaction committed
    # but whose start task was lost before a worker claimed execution.
    pending_cutoff = timezone.now() - timedelta(seconds=stale_seconds)
    pending = ApplicationInstance.objects.filter(
        status=ApplicationStatus.PENDING,
        created_at__lt=pending_cutoff,
        execution_task_id="",
        cancel_requested=False,
    ).exclude(
        stage="deletion_pending",
    ).only("pk")
    pending_requeued = 0
    for pending_instance in pending.iterator():
        try:
            start_application_installation.delay(str(pending_instance.pk))
            pending_requeued += 1
        except Exception:
            logger.warning(
                "Unable to requeue pending application coordinator %s; broker may still be unavailable.",
                pending_instance.pk, exc_info=True,
            )

    return {
        "applications": instances.count(),
        "recovered_dispatches": recovered,
        "pending_requeued": pending_requeued,
    }
