"""Small immutable execution context shared by deployment strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from deployments.common.exceptions import DeploymentCancelled, StaleDeploymentWorkerError
from deployments.runtime.contract import RuntimeSelection


@dataclass(frozen=True)
class DeploymentExecutionEvent:
    deployment_id: str
    service_id: str
    revision_id: str | None
    operation_key: str
    stage: str
    level: str = "info"
    message: str = ""
    progress: int | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeploymentExecutionContext:
    """Identity, fencing, cancellation, and event ports for one attempt."""

    deployment_id: str
    service_id: str
    revision_id: str | None
    worker_task_id: str | None
    operation_key: str
    runtime_selection: RuntimeSelection
    owns_execution: Callable[[], bool] = field(default=lambda: True, compare=False, repr=False)
    cancellation_requested: Callable[[], bool] = field(default=lambda: False, compare=False, repr=False)
    publish: Callable[[DeploymentExecutionEvent], None] = field(
        default=lambda event: None,
        compare=False,
        repr=False,
    )

    def operation(self, suffix: str) -> str:
        return f"{self.operation_key}:{suffix}"

    def assert_owner(self) -> None:
        if not self.owns_execution():
            raise StaleDeploymentWorkerError(
                "Deployment execution ownership is no longer current.",
                details={
                    "deployment_id": self.deployment_id,
                    "service_id": self.service_id,
                    "worker_task_id": self.worker_task_id,
                    "operation_key": self.operation_key,
                },
            )

    def assert_can_continue(self) -> None:
        self.assert_owner()
        if self.cancellation_requested():
            raise DeploymentCancelled(
                "Deployment cancellation was requested at a safe execution boundary.",
                details={
                    "deployment_id": self.deployment_id,
                    "operation_key": self.operation_key,
                },
            )

    def emit(
        self,
        stage: str,
        message: str = "",
        *,
        level: str = "info",
        progress: int | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        event = DeploymentExecutionEvent(
            deployment_id=self.deployment_id,
            service_id=self.service_id,
            revision_id=self.revision_id,
            operation_key=self.operation_key,
            stage=stage,
            level=level,
            message=message,
            progress=progress,
            details=dict(details or {}),
        )
        # Observability must not corrupt deployment execution.  The concrete
        # event publisher performs its own redaction and persistence policy.
        try:
            self.publish(event)
        except Exception:
            return
