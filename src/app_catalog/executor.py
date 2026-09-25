from __future__ import annotations

import logging
import uuid
from pathlib import Path
from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from deploy.models import DeploymentStatusChoices
from deployments.core.state.manager import StateManager

from .catalog import ApplicationCatalog, CatalogDefinition, resolve_variant
from .models import ApplicationInstance, ApplicationInstanceService, ApplicationStatus
from .plan import ApplicationPlan, plan_from_resolved, ready_service_keys

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServiceDispatch:
    binding_id: int
    instance_id: str
    service_key: str
    task_id: str


class ApplicationStackExecutor:
    """Coordinates child Deploy executions without replacing the Deploy engine.

    The executor owns only application-level coordination: dependency ordering,
    parallel dispatch, cancellation propagation, timeout convergence, and
    application-level terminal state. Individual Deploy rows remain the source
    of truth for Docker/build/readiness execution.
    """

    def __init__(self, instance_id: str):
        self.instance_id = str(instance_id)

    def _load(self) -> tuple[ApplicationInstance, ApplicationPlan]:
        instance = ApplicationInstance.objects.prefetch_related(
            "services__deploy", "services__service"
        ).get(pk=self.instance_id)
        if instance.definition_snapshot:
            definition = CatalogDefinition(
                data=dict(instance.definition_snapshot),
                source=Path(f"<installed:{instance.catalog_id}>"),
            )
        else:
            # Backward compatibility for installations created before immutable
            # definition snapshots were introduced.
            definition = ApplicationCatalog.get(instance.catalog_id)
        supplied = dict(instance.config or {})
        supplied.update(instance.secret_config or {})
        resolved = resolve_variant(definition, instance.variant_id, supplied)
        resolved["config"]["slug"] = instance.slug
        return instance, plan_from_resolved(resolved)

    @staticmethod
    def _timeout_minutes() -> int:
        try:
            return max(1, int(getattr(settings, "CATALOG_APPLICATION_TIMEOUT_MINUTES", 60)))
        except (TypeError, ValueError):
            return 60

    def start(self, *, task_id: str | None = None) -> bool:
        """Claim application execution exactly once.

        A duplicate Celery delivery must not overwrite the owner task id or
        restart an already-running application coordinator.
        """
        now = timezone.now()
        deadline = now + timedelta(minutes=self._timeout_minutes())
        with transaction.atomic():
            instance = ApplicationInstance.objects.select_for_update().get(pk=self.instance_id)
            if instance.status in {ApplicationStatus.RUNNING, ApplicationStatus.FAILED, ApplicationStatus.CANCELLED}:
                return False
            if instance.status == ApplicationStatus.DEPLOYING:
                current_owner = str(instance.execution_task_id or "")
                requested_owner = str(task_id or "")
                if current_owner and requested_owner and current_owner != requested_owner:
                    return False
                return True
            instance.status = ApplicationStatus.DEPLOYING
            instance.stage = "dependency_resolution"
            instance.started_at = instance.started_at or now
            instance.execution_deadline = instance.execution_deadline or deadline
            if task_id:
                instance.execution_task_id = str(task_id)
            instance.save(update_fields=[
                "status", "stage", "started_at", "execution_deadline",
                "execution_task_id", "updated_at",
            ])
            return True

    def cancel(self, *, reason: str = "Application deployment cancelled.") -> None:
        with transaction.atomic():
            instance = ApplicationInstance.objects.select_for_update().get(pk=self.instance_id)
            if instance.status in {ApplicationStatus.RUNNING, ApplicationStatus.FAILED, ApplicationStatus.CANCELLED}:
                return
            instance.cancel_requested = True
            instance.stage = "cancellation_requested"
            instance.error_code = "APPLICATION_DEPLOYMENT_CANCELLED"
            instance.error_message = reason
            instance.save(update_fields=[
                "cancel_requested", "stage", "error_code", "error_message", "updated_at",
            ])
            rows = list(
                ApplicationInstanceService.objects.select_related("deploy")
                .select_for_update()
                .filter(instance_id=self.instance_id)
            )

        for binding in rows:
            deploy = binding.deploy
            if deploy.status in {
                DeploymentStatusChoices.PENDING,
                DeploymentStatusChoices.RUNNING,
                DeploymentStatusChoices.ROLLING_BACK,
            }:
                deploy.cancel_requested = True
                deploy.save(update_fields=["cancel_requested", "updated_at"])
                if deploy.status == DeploymentStatusChoices.PENDING:
                    try:
                        StateManager.transition_deploy(
                            deploy.pk,
                            DeploymentStatusChoices.CANCELLED,
                            update_fields={
                                "stage": "cancelled",
                                "progress": 100,
                                "status_message": "Service was not started because the application was cancelled.",
                            },
                        )
                    except Exception:
                        logger.exception("Unable to cancel pending child deploy %s", deploy.pk)

    def _dependency_map(self, plan: ApplicationPlan) -> dict[str, set[str]]:
        return {svc.key: set(svc.dependencies) for svc in plan.services}

    def _reconcile_terminal(self, instance: ApplicationInstance, plan: ApplicationPlan) -> bool:
        with transaction.atomic():
            locked = ApplicationInstance.objects.select_for_update().get(pk=self.instance_id)
            if locked.status in {ApplicationStatus.FAILED, ApplicationStatus.CANCELLED, ApplicationStatus.RUNNING}:
                return True
            bindings = list(ApplicationInstanceService.objects.select_related("deploy").filter(instance_id=self.instance_id))
            required = {svc.key: svc.required for svc in plan.services}
            failed = [b for b in bindings if required.get(b.service_key, True) and b.deploy.status in {DeploymentStatusChoices.FAILED, DeploymentStatusChoices.ROLLED_BACK, DeploymentStatusChoices.CANCELLED}]
            if locked.cancel_requested:
                active = [b for b in bindings if b.deploy.status in {DeploymentStatusChoices.PENDING, DeploymentStatusChoices.RUNNING, DeploymentStatusChoices.ROLLING_BACK}]
                if not active:
                    locked.status = ApplicationStatus.CANCELLED
                    locked.stage = "cancelled"
                    locked.error_code = locked.error_code or "APPLICATION_DEPLOYMENT_CANCELLED"
                    locked.error_message = locked.error_message or "Application deployment cancelled."
                    locked.deployed_at = None
                    locked.save(update_fields=["status", "stage", "error_code", "error_message", "deployed_at", "updated_at"])
                    return True
                return False
            if failed:
                first = failed[0]
                message = first.deploy.error_message or first.deploy.status_message or "Service deployment did not complete."
                downstream = [b.service_key for b in bindings if b.deploy.status == DeploymentStatusChoices.PENDING]
                if downstream:
                    message += " Dependent services were not started: " + ", ".join(sorted(downstream)) + "."
                locked.status = ApplicationStatus.FAILED
                locked.stage = "service_failed"
                locked.error_code = "APPLICATION_SERVICE_DEPLOYMENT_FAILED"
                locked.error_message = f"{first.service_key}: {message}"
                locked.save(update_fields=["status", "stage", "error_code", "error_message", "updated_at"])
                for binding in bindings:
                    if binding.deploy.status == DeploymentStatusChoices.RUNNING:
                        binding.deploy.cancel_requested = True
                        binding.deploy.save(update_fields=["cancel_requested", "updated_at"])
                return True
            required_bindings = [b for b in bindings if required.get(b.service_key, True)]
            if required_bindings and all(b.deploy.status == DeploymentStatusChoices.SUCCEEDED for b in required_bindings):
                locked.status = ApplicationStatus.RUNNING
                locked.stage = "application_ready"
                locked.error_code = ""
                locked.error_message = ""
                locked.deployed_at = timezone.now()
                locked.save(update_fields=["status", "stage", "error_code", "error_message", "deployed_at", "updated_at"])
                return True
            return False

    def reconcile(self) -> list[ServiceDispatch]:
        instance, plan = self._load()
        bindings = list(
            ApplicationInstanceService.objects.select_related("deploy")
            .filter(instance_id=self.instance_id)
        )
        by_key = {b.service_key: b for b in bindings}
        if set(by_key) != {s.key for s in plan.services}:
            raise ValueError("Application instance service bindings do not match its application plan.")

        now = timezone.now()
        should_cancel = False
        cancel_reason = "Application deployment cancelled."
        with transaction.atomic():
            locked = ApplicationInstance.objects.select_for_update().get(pk=self.instance_id)
            if locked.status in {ApplicationStatus.FAILED, ApplicationStatus.CANCELLED, ApplicationStatus.RUNNING}:
                return []
            if locked.execution_deadline and now >= locked.execution_deadline:
                locked.cancel_requested = True
                locked.stage = "timeout_requested"
                locked.error_code = "APPLICATION_DEPLOYMENT_TIMEOUT"
                locked.error_message = "The application deployment exceeded its maximum allowed time."
                locked.save(update_fields=[
                    "cancel_requested", "stage", "error_code", "error_message", "updated_at",
                ])
            should_cancel = bool(locked.cancel_requested)
            cancel_reason = locked.error_message or cancel_reason

        # Re-read the authoritative locked state above. Do not rely on the
        # earlier unlocked instance snapshot; a concurrent API cancellation
        # must stop scheduling new child services in this reconciliation.
        if should_cancel:
            self.cancel(reason=cancel_reason)
            latest, _ = self._load()
            self._reconcile_terminal(latest, plan)
            return []

        if self._reconcile_terminal(instance, plan):
            return []

        dispatches: list[ServiceDispatch] = []
        bindings = list(
            ApplicationInstanceService.objects.select_related("deploy")
            .filter(instance_id=self.instance_id)
        )
        status_by_key = {b.service_key: b.deploy.status for b in bindings}
        claimed = {b.service_key for b in bindings if b.dispatched_at is not None}
        ready_keys = set(ready_service_keys(plan, status_by_key, claimed))
        stale_before = now - timedelta(seconds=300)

        with transaction.atomic():
            locked = ApplicationInstance.objects.select_for_update().get(pk=self.instance_id)
            if locked.status in {ApplicationStatus.FAILED, ApplicationStatus.CANCELLED, ApplicationStatus.RUNNING}:
                return []
            if locked.cancel_requested or (locked.execution_deadline and now >= locked.execution_deadline):
                return []
            for binding in ApplicationInstanceService.objects.select_for_update().select_related("deploy").filter(instance_id=self.instance_id):
                if binding.dispatched_at is not None and binding.dispatched_at < stale_before and binding.deploy.status == DeploymentStatusChoices.PENDING:
                    binding.dispatched_at = None
                    binding.save(update_fields=["dispatched_at"])
                if binding.dispatched_at is not None:
                    continue
                deploy = binding.deploy
                if deploy.status != DeploymentStatusChoices.PENDING:
                    continue
                if binding.service_key not in ready_keys:
                    continue
                token = str(uuid.uuid4())
                binding.dispatch_task_id = token
                binding.dispatched_at = now
                binding.save(update_fields=["dispatch_task_id", "dispatched_at"])
                dispatches.append(ServiceDispatch(
                    binding_id=binding.pk,
                    instance_id=self.instance_id,
                    service_key=binding.service_key,
                    task_id=token,
                ))
            if dispatches:
                locked.stage = "dispatching_services"
                locked.save(update_fields=["stage", "updated_at"])

        return dispatches


__all__ = ["ApplicationStackExecutor", "ServiceDispatch"]
