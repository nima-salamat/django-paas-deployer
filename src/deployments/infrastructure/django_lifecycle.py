"""Django adapter for the framework-neutral deployment lifecycle executor."""

from __future__ import annotations

from typing import Mapping

from django.db import transaction
from django.utils import timezone

from deploy.models import Deploy
from deployments.common.exceptions import DeploymentCancelled, StaleDeploymentWorkerError
from deployments.application.context import DeploymentExecutionContext
from deployments.core.state.manager import ActivationOutcome
from deployments.core.state.manager import StateManager
from deployments.common import state_machine as sm


class DjangoDeploymentLifecycleStore:
    """Persist lifecycle transitions through the fenced ``StateManager``."""

    def __init__(
        self,
        deployment_id: int,
        *,
        task_id: str | None = None,
        expected_active_revision_id: str | None = None,
        allow_active_revision_replacement: bool = False,
    ) -> None:
        self.deployment_id = deployment_id
        self.task_id = task_id
        self.expected_active_revision_id = expected_active_revision_id
        self.allow_active_revision_replacement = bool(allow_active_revision_replacement)
        self.last_activation_outcome: str | None = None

    @property
    def status(self) -> str:
        value = (
            Deploy.objects
            .filter(pk=self.deployment_id)
            .values_list("status", flat=True)
            .first()
        )
        return value or sm.DEPLOY_FAILED

    def ensure_running(self, context: DeploymentExecutionContext) -> bool:
        if self.is_terminal():
            return False
        context.assert_owner()
        if self.status == sm.DEPLOY_RUNNING:
            return True
        transitioned = StateManager.transition_deploy_if_owned(
            self.deployment_id,
            sm.DEPLOY_RUNNING,
            task_id=self.task_id or context.worker_task_id,
            update_fields={"stage": "deployment_started"},
        )
        # The state manager can turn this request into CANCELLED when the
        # token was set before its row lock was acquired.  Do not let the
        # executor continue planning after that terminal decision.
        return transitioned and self.status == sm.DEPLOY_RUNNING

    def transition(
        self,
        context: DeploymentExecutionContext,
        target: str,
        *,
        message: str = "",
        details: Mapping[str, object] | None = None,
    ) -> bool:
        self.last_activation_outcome = None
        if not context.owns_execution():
            return False
        updates = {"status_message": message[:500]}
        if details:
            updates["error_message"] = str(details.get("error_message") or "")[:1000]
            if "reconciliation_required" in details:
                updates["reconciliation_required"] = bool(details.get("reconciliation_required"))
            if "cleanup_failed" in details:
                cleanup_failed = bool(details.get("cleanup_failed"))
                cleanup_attempted = bool(details.get("cleanup_attempted"))
                updates["cleanup_status"] = (
                    "critical"
                    if cleanup_failed
                    else ("clean" if cleanup_attempted else "not_required")
                )
                updates["cleanup_failures"] = list(details.get("cleanup_failures") or [])
        if target == sm.DEPLOY_FAILED and bool((details or {}).get("recoverable")):
            return StateManager.mark_deploy_retry_pending(
                self.deployment_id,
                task_id=str(self.task_id or context.worker_task_id or ""),
                message=message or "A temporary deployment failure occurred; retry is pending.",
                error_message=str(
                    (details or {}).get("technical_message")
                    or (details or {}).get("error_message")
                    or message
                    or ""
                ),
                stage="retry_pending",
                update_fields=updates,
                event_payload={
                    "trace_id": str(context.operation_key),
                    "details": {
                        **dict(details or {}),
                        "recoverable": True,
                        "retry_pending": True,
                    },
                },
            )

        terminal = sm.is_deploy_terminal(target)
        if target == sm.DEPLOY_SUCCEEDED:
            event_payload = {
                "event_id": str(__import__("uuid").uuid4()),
                "trace_id": str(context.operation_key),
                "deployment_id": str(context.deployment_id),
                "service_id": str(context.service_id),
                "revision_id": str(context.revision_id or ""),
                "task_id": str(self.task_id or context.worker_task_id or ""),
                "event_type": "deployment.succeeded.info",
                "stage": "finished",
                "level": "info",
                "message": message or "Deployment completed successfully.",
                "progress": 100,
                "details": dict(details or {}),
            }
            activation_outcome: dict[str, str] = {}
            committed = StateManager.activate_revision_and_succeed(
                int(self.deployment_id),
                context.revision_id,
                task_id=self.task_id or context.worker_task_id,
                expected_lifecycle_generation=context.expected_lifecycle_generation,
                expected_previous_deploy_id=context.expected_previous_deploy_id,
                enforce_previous_deploy=context.enforce_previous_deploy,
                expected_active_revision_id=self.expected_active_revision_id,
                allow_active_revision_replacement=self.allow_active_revision_replacement,
                outcome=activation_outcome,
                update_fields={**updates, "stage": "finished", "progress": 100},
                event_payload=event_payload,
            )
            self.last_activation_outcome = activation_outcome.get("value")
            return committed
        event_payload = None
        if terminal:
            import uuid
            event_payload = {
                "event_id": str(uuid.uuid4()),
                "trace_id": str(context.operation_key),
                "deployment_id": str(context.deployment_id),
                "service_id": str(context.service_id),
                "revision_id": str(context.revision_id or ""),
                "task_id": str(self.task_id or context.worker_task_id or ""),
                "event_type": f"deployment.{target}.info",
                "stage": target,
                "level": "info" if target == sm.DEPLOY_SUCCEEDED else "error",
                "message": message,
                "progress": 100,
                "details": dict(details or {}),
            }
        return StateManager.transition_deploy_if_owned(
            self.deployment_id,
            target,
            task_id=self.task_id or context.worker_task_id,
            update_fields=updates,
            terminal=terminal,
            event_payload=event_payload,
        )

    def journal_runtime_resource(
        self,
        context: DeploymentExecutionContext,
        *,
        kind: str,
        name: str,
        runtime_id: str = "",
        state: str = "active",
        metadata: Mapping[str, object] | None = None,
        error: str = "",
    ) -> None:
        """Record runtime ownership only while this worker still owns the lifecycle."""
        from deploy.models import DeploymentResource
        from services.models import Service

        if not name:
            return
        task_id = str(self.task_id or context.worker_task_id or "").strip()
        if not task_id:
            context.assert_can_continue()

        with transaction.atomic():
            deploy = (
                Deploy.objects.select_for_update()
                .filter(pk=self.deployment_id)
                .first()
            )
            if deploy is None:
                raise StaleDeploymentWorkerError(
                    "Cannot journal a runtime resource for a missing deployment.",
                    details={"deployment_id": str(self.deployment_id)},
                )
            service = (
                Service.objects.select_for_update()
                .filter(pk=deploy.service_id)
                .first()
            )
            activation_commit = (
                state == "active"
                and deploy.status == sm.DEPLOY_SUCCEEDED
            )
            cleanup_commit = state in {"retired", "cleanup_pending"}
            if service is None or (
                not activation_commit
                and task_id
                and (
                    str(deploy.execution_task_id or "") != task_id
                    or str(service.task_id or "") != task_id
                )
            ):
                raise StaleDeploymentWorkerError(
                    "Cannot journal a runtime resource after deployment ownership was lost.",
                    details={
                        "deployment_id": str(self.deployment_id),
                        "service_id": str(deploy.service_id),
                        "worker_task_id": task_id,
                    },
                )
            if sm.is_deploy_terminal(deploy.status) and not activation_commit:
                raise StaleDeploymentWorkerError(
                    "Cannot journal a runtime resource after deployment became terminal.",
                    details={
                        "deployment_id": str(self.deployment_id),
                        "status": str(deploy.status),
                    },
                )
            if deploy.cancel_requested and not (activation_commit or cleanup_commit):
                raise DeploymentCancelled(
                    "Deployment cancellation was requested before runtime resource journaling.",
                    details={"deployment_id": str(self.deployment_id)},
                )
            expected_generation = context.expected_lifecycle_generation
            actual_generation = int(getattr(service, "lifecycle_generation", 0) or 0)
            if (
                expected_generation is not None
                and actual_generation != int(expected_generation)
            ):
                raise StaleDeploymentWorkerError(
                    "Cannot journal a runtime resource after the service lifecycle generation changed.",
                    details={
                        "deployment_id": str(self.deployment_id),
                        "service_id": str(service.pk),
                        "expected_lifecycle_generation": int(expected_generation),
                        "actual_lifecycle_generation": actual_generation,
                    },
                )
            if activation_commit and str(service.active_revision_id or "") != str(context.revision_id or ""):
                raise StaleDeploymentWorkerError(
                    "Cannot mark a runtime resource active unless its revision is authoritative.",
                    details={
                        "deployment_id": str(self.deployment_id),
                        "service_id": str(service.pk),
                        "revision_id": str(context.revision_id or ""),
                        "active_revision_id": str(service.active_revision_id or ""),
                    },
                )
            DeploymentResource.objects.update_or_create(
                deployment_id=int(self.deployment_id),
                kind=str(kind)[:64],
                name=str(name)[:255],
                defaults={
                    "runtime_id": str(runtime_id or "")[:255],
                    "state": str(state)[:32],
                    "owned": True,
                    "metadata": dict(metadata or {}),
                    "last_error": str(error or "")[:2000],
                    "retired_at": timezone.now() if state == "retired" else None,
                },
            )

    def record_finalization(
        self,
        context: DeploymentExecutionContext,
        details: Mapping[str, object] | None = None,
    ) -> bool:
        """Persist post-activation cleanup state without reopening Deploy status."""
        from deploy.models import Deploy
        from services.models import Service

        details = dict(details or {})
        with transaction.atomic():
            deploy = Deploy.objects.select_for_update().filter(pk=self.deployment_id).first()
            if deploy is None or deploy.status != sm.DEPLOY_SUCCEEDED:
                return False
            service = Service.objects.select_for_update().filter(pk=deploy.service_id).first()
            if service is None:
                return False
            expected_generation = context.expected_lifecycle_generation
            if (
                expected_generation is not None
                and int(getattr(service, "lifecycle_generation", 0) or 0)
                != int(expected_generation)
            ):
                return False
            if str(service.active_revision_id or "") != str(context.revision_id or ""):
                return False
            cleanup_failed = bool(details.get("cleanup_failed"))
            journal_failed = bool(details.get("journal_update_failed"))
            reconciliation_required = bool(
                details.get("reconciliation_required") or cleanup_failed or journal_failed
            )
            cleanup_status = (
                "critical"
                if cleanup_failed or journal_failed
                else ("clean" if details.get("cleanup_attempted") else "not_required")
            )
            Deploy.objects.filter(pk=deploy.pk, status=sm.DEPLOY_SUCCEEDED).update(
                reconciliation_required=reconciliation_required,
                cleanup_status=cleanup_status,
                cleanup_failures=list(details.get("cleanup_failures") or []),
                updated_at=timezone.now(),
            )
            return True

    def is_terminal(self) -> bool:
        return sm.is_deploy_terminal(self.status)


__all__ = ["DjangoDeploymentLifecycleStore"]

