
"""Generation-aware reconciliation execution boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from deployments.common.exceptions import StaleDeploymentWorkerError
from deployments.runtime.contract import RuntimeContract, RuntimeHandle, RuntimeOperationResult, RuntimeSelection
from deployments.runtime.errors import RuntimeUnavailableError, RuntimeUnsupportedError

from .planner import DesiredRuntimeState, ReconciliationAction, ReconciliationDecision


@dataclass(frozen=True)
class ReconciliationExecutionContext:
    service_id: str
    lifecycle_generation: int | str
    active_revision_id: str | None
    owns_execution: Callable[[], bool]
    current_generation: Callable[[], int | str] | None = None

    def assert_current(self) -> None:
        if not self.owns_execution():
            raise StaleDeploymentWorkerError(
                "Reconciliation execution no longer owns this service."
            )
        if self.current_generation is not None:
            observed = self.current_generation()
            if str(observed) != str(self.lifecycle_generation):
                raise StaleDeploymentWorkerError(
                    "Reconciliation was generated for a stale lifecycle generation."
                )


class ReconciliationExecutor:
    """Perform one pure planner decision against a runtime, with fencing."""

    def execute(
        self,
        decision: ReconciliationDecision,
        *,
        desired: DesiredRuntimeState,
        selection: RuntimeSelection,
        runtime: RuntimeContract,
        context: ReconciliationExecutionContext,
        plan: Any | None = None,
        handle: RuntimeHandle | None = None,
    ) -> RuntimeOperationResult | None:
        context.assert_current()

        missing = selection.capabilities.missing(*desired.required_capabilities)
        if missing:
            raise RuntimeUnsupportedError(
                "The selected runtime cannot satisfy the reconciliation decision.",
                details={"missing": sorted(item.value for item in missing)},
            )
        if not selection.availability.can_execute:
            raise RuntimeUnavailableError(
                selection.availability.message
                or "The selected runtime is unavailable for reconciliation.",
                code=selection.availability.reason_code or "runtime_unavailable",
            )

        action = decision.action
        if action in {
            ReconciliationAction.CONVERGED,
            ReconciliationAction.BLOCKED,
            ReconciliationAction.MANUAL_INTERVENTION,
        }:
            return None

        operation_key = self._operation_key(
            desired=desired,
            decision=decision,
            lifecycle_generation=context.lifecycle_generation,
        )
        context.assert_current()

        if action is ReconciliationAction.STOP:
            if handle is None:
                raise ValueError("STOP reconciliation requires an identified runtime handle.")
            if not handle.runtime_id:
                raise StaleDeploymentWorkerError(
                    "Destructive reconciliation requires a runtime resource identity."
                )
            if str(handle.identity.service_id) != str(desired.service_id):
                raise StaleDeploymentWorkerError(
                    "Runtime resource identity does not belong to the desired service."
                )
            result = runtime.stop(handle, operation_key=operation_key)
        elif action in {
            ReconciliationAction.CREATE,
            ReconciliationAction.UPDATE,
            ReconciliationAction.REPAIR,
        }:
            if plan is None:
                raise ValueError(
                    f"{action.value.upper()} reconciliation requires a native DeploymentPlan."
                )
            plan_identity = getattr(plan, "identity", None)
            if plan_identity is not None and str(getattr(plan_identity, "service_id", "")) != str(desired.service_id):
                raise StaleDeploymentWorkerError(
                    "Reconciliation plan identity does not belong to the desired service."
                )
            result = runtime.apply(
                plan,
                operation_key=operation_key,
            )
        else:
            raise ValueError(f"Unsupported reconciliation action: {action.value}")

        context.assert_current()
        return result

    @staticmethod
    def _operation_key(
        *,
        desired: DesiredRuntimeState,
        decision: ReconciliationDecision,
        lifecycle_generation: int | str,
    ) -> str:
        revision = str(desired.revision_id or "none")
        return (
            f"reconcile:{desired.service_id}:"
            f"generation:{lifecycle_generation}:"
            f"revision:{revision}:"
            f"action:{decision.action.value}"
        )


__all__ = ["ReconciliationExecutionContext", "ReconciliationExecutor"]
