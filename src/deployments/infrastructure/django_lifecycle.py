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
        return StateManager.transition_deploy_if_owned(
            self.deployment_id,
            sm.DEPLOY_RUNNING,
            task_id=self.task_id or context.worker_task_id,
            update_fields={"stage": "deployment_started"},
        )

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
        return StateManager.transition_deploy_if_owned(
            self.deployment_id,
            target,
            task_id=self.task_id or context.worker_task_id,
            update_fields=updates,
            terminal=sm.is_deploy_terminal(target),
        )

    def is_terminal(self) -> bool:
        return sm.is_deploy_terminal(self.status)


__all__ = ["DjangoDeploymentLifecycleStore"]
