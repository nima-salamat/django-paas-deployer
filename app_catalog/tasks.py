from __future__ import annotations

import logging
import uuid
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from deployments.celery.tasks import deploy_task
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


def _schedule_next(instance_id: str, current_key: str | None = None):
    """Reconcile the application DAG and dispatch every currently-ready service."""
    executor = ApplicationStackExecutor(instance_id)
    dispatches = executor.reconcile()
    for dispatch in dispatches:
        try:
            gate_application_service.apply_async(
                args=[dispatch.instance_id, dispatch.service_key],
                task_id=dispatch.task_id,
            )
        except Exception:
            logger.exception(
                "Unable to queue application service %s/%s",
                dispatch.instance_id, dispatch.service_key,
            )
            # Clear the dispatch claim so the periodic reconciler can safely
            # retry this service without creating a duplicate task.
            ApplicationInstanceService.objects.filter(
                pk=dispatch.binding_id,
                dispatched_at__isnull=False,
            ).update(dispatched_at=None)



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
                   .select_related("deploy", "service", "instance")
                   .filter(instance_id=instance_id, service_key=service_key).first())
        if not instance or not binding:
            return
        if instance.status != ApplicationStatus.DEPLOYING or instance.cancel_requested:
            binding.dispatched_at = None
            binding.dispatch_task_id = ""
            binding.save(update_fields=["dispatched_at", "dispatch_task_id"])
            return
        if binding.dispatch_task_id and binding.dispatch_task_id != str(self.request.id):
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
            transaction.on_commit(lambda: deploy_task.apply_async(args=[str(binding.deploy_id)], link=callback, link_error=failure, task_id=child_task_id))
        except Exception as exc:
            logger.exception("Application service gate failed for %s/%s", instance_id, service_key)
            binding.dispatched_at = None
            binding.dispatch_task_id = ""
            binding.save(update_fields=["dispatched_at", "dispatch_task_id"])
            _mark_instance_failed(instance_id, f"{service_key}: {to_deployment_error(exc, stage='application_orchestration').user_message}", "APPLICATION_PLAN_INVALID")


@shared_task(name="app_catalog.advance_application_service")
def advance_application_service(instance_id: str, service_key: str, child_task_id: str | None = None):
    with transaction.atomic():
        binding = ApplicationInstanceService.objects.select_for_update().filter(instance_id=instance_id, service_key=service_key).first()
        if not binding or (child_task_id and binding.dispatch_task_id != child_task_id):
            return
        binding.dispatched_at = None
        binding.dispatch_task_id = ""
        binding.save(update_fields=["dispatched_at", "dispatch_task_id"])
    _schedule_next(instance_id, current_key=service_key)


@shared_task(name="app_catalog.application_service_failed")
def application_service_failed(instance_id: str, service_key: str, child_task_id: str | None = None, *args, **kwargs):
    with transaction.atomic():
        binding = ApplicationInstanceService.objects.select_for_update().filter(instance_id=instance_id, service_key=service_key).first()
        if not binding or (child_task_id and binding.dispatch_task_id != child_task_id):
            return
        binding.dispatched_at = None
        binding.dispatch_task_id = ""
        binding.save(update_fields=["dispatched_at", "dispatch_task_id"])
    _schedule_next(instance_id, current_key=service_key)


@shared_task(name="app_catalog.cancel_application_installation")
def cancel_application_installation(instance_id: str, reason: str = "Application deployment cancelled by user request."):
    ApplicationStackExecutor(instance_id).cancel(reason=reason)
    _schedule_next(instance_id)


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
    instances = ApplicationInstance.objects.filter(status=ApplicationStatus.DEPLOYING).only("pk")
    recovered = 0
    for instance in instances.iterator():
        # A cancellation task can be lost after the API commits the flag.
        # Re-apply cancellation from the periodic reconciler so child
        # deployments cannot remain active forever.
        try:
            fresh = ApplicationInstance.objects.only("status", "cancel_requested").get(pk=instance.pk)
            if fresh.cancel_requested:
                ApplicationStackExecutor(str(instance.pk)).cancel(
                    reason="Application deployment cancelled by user request."
                )
        except ApplicationInstance.DoesNotExist:
            continue

        stale = ApplicationInstanceService.objects.filter(
            instance_id=instance.pk,
            dispatched_at__lt=cutoff,
            deploy__status=DeploymentStatusChoices.PENDING,
        )
        if stale.exists():
            stale.update(dispatched_at=None)
            recovered += stale.count()
        try:
            _schedule_next(str(instance.pk))
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
