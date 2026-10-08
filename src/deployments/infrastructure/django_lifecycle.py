"""Django adapter for the framework-neutral deployment lifecycle executor."""

from __future__ import annotations

from typing import Mapping

from deploy.models import Deploy
from deployments.application.context import DeploymentExecutionContext
from deployments.core.state.manager import StateManager
from deployments.common import state_machine as sm


class DjangoDeploymentLifecycleStore:
    """Persist lifecycle transitions through the fenced ``StateManager``."""

    def __init__(self, deployment_id: int, *, task_id: str | None = None) -> None:
        self.deployment_id = deployment_id
        self.task_id = task_id

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
            return StateManager.activate_revision_and_succeed(
                int(self.deployment_id),
                context.revision_id,
                task_id=self.task_id or context.worker_task_id,
                expected_lifecycle_generation=context.expected_lifecycle_generation,
                expected_previous_deploy_id=context.expected_previous_deploy_id,
                enforce_previous_deploy=context.enforce_previous_deploy,
                update_fields={**updates, "stage": "finished", "progress": 100},
                event_payload=event_payload,
            )
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
    ) -> None:
        """Record external runtime ownership without opening a long transaction."""
        from deploy.models import DeploymentResource

        if not name:
            return
        DeploymentResource.objects.update_or_create(
            deployment_id=int(self.deployment_id),
            kind=str(kind)[:64],
            name=str(name)[:255],
            defaults={
                "runtime_id": str(runtime_id or "")[:255],
                "state": str(state)[:32],
                "owned": True,
                "metadata": dict(metadata or {}),
                "last_error": "",
            },
        )

    def is_terminal(self) -> bool:
        return sm.is_deploy_terminal(self.status)


__all__ = ["DjangoDeploymentLifecycleStore"]
