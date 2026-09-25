"""Common deployment lifecycle executor.

The executor owns lifecycle sequencing and fencing.  A strategy owns how a
plan is built and activated; a runtime adapter owns external runtime calls.
Neither application nor database strategy needs to duplicate this state
machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from deployments.common import state_machine as sm
from deployments.common.exceptions import (
    DeploymentCancelled,
    DeploymentError,
    StaleDeploymentWorkerError,
    to_deployment_error,
)
from deployments.runtime.contract import RuntimeContract, RuntimeHandle, RuntimeOperationResult
from deployments.runtime.errors import (
    RuntimeOperationError,
    RuntimeUnavailableError,
    RuntimeUnsupportedError,
)

from .context import DeploymentExecutionContext


class DeploymentStrategy(Protocol):
    """Strategy-specific planning and activation hooks."""

    def plan(self, context: DeploymentExecutionContext) -> Any:
        ...

    def activate(
        self,
        context: DeploymentExecutionContext,
        plan: Any,
        readiness: RuntimeOperationResult,
    ) -> None:
        ...


class LifecycleStore(Protocol):
    """Persistence port for the authoritative deployment state manager."""

    status: str

    def ensure_running(self, context: DeploymentExecutionContext) -> bool:
        ...

    def transition(
        self,
        context: DeploymentExecutionContext,
        target: str,
        *,
        message: str = "",
        details: Mapping[str, Any] | None = None,
    ) -> bool:
        ...

    def is_terminal(self) -> bool:
        ...


@dataclass(frozen=True)
class DeploymentLifecycleResult:
    status: str
    success: bool
    retryable: bool = False
    runtime_result: RuntimeOperationResult | None = None
    error: DeploymentError | None = None
    rollback_performed: bool = False
    rollback_failed: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)


class InMemoryLifecycleStore:
    """Reference lifecycle store used to prove executor semantics quickly."""

    def __init__(self, *, status: str = sm.DEPLOY_PENDING) -> None:
        self.status = status
        self.history: list[tuple[str, str]] = []
        self.details: dict[str, Any] = {}

    def ensure_running(self, context: DeploymentExecutionContext) -> bool:
        if self.is_terminal():
            return False
        context.assert_owner()
        if self.status == sm.DEPLOY_PENDING:
            self._transition(sm.DEPLOY_RUNNING, message="Deployment execution started.")
        elif self.status != sm.DEPLOY_RUNNING:
            sm.check_deploy_transition(self.status, sm.DEPLOY_RUNNING)
            self._transition(sm.DEPLOY_RUNNING, message="Deployment execution started.")
        return True

    def transition(
        self,
        context: DeploymentExecutionContext,
        target: str,
        *,
        message: str = "",
        details: Mapping[str, Any] | None = None,
    ) -> bool:
        if not context.owns_execution():
            return False
        # The final state writer re-checks cancellation while the transition
        # is serialized.  This is the pure equivalent of the DB CAS fence.
        if target != sm.DEPLOY_CANCELLED and context.cancellation_requested():
            target = sm.DEPLOY_CANCELLED
            message = "Deployment cancelled by the user."
        sm.check_deploy_transition(self.status, target)
        self._transition(target, message=message, details=details)
        return True

    def is_terminal(self) -> bool:
        return sm.is_deploy_terminal(self.status)

    def _transition(
        self,
        target: str,
        *,
        message: str = "",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        previous = self.status
        self.status = target
        self.history.append((previous, target))
        self.details = {"message": message, **dict(details or {})}


class DeploymentLifecycleExecutor:
    """Execute one strategy through the shared lifecycle contract."""

    def __init__(self, store: LifecycleStore) -> None:
        self.store = store

    def execute(
        self,
        context: DeploymentExecutionContext,
        strategy: DeploymentStrategy,
        runtime: RuntimeContract,
        *,
        readiness_timeout: float | None = None,
    ) -> DeploymentLifecycleResult:
        if not self.store.ensure_running(context):
            return DeploymentLifecycleResult(
                status=self.store.status,
                success=self.store.status == sm.DEPLOY_SUCCEEDED,
            )

        plan = None
        handle: RuntimeHandle | None = None
        applied: RuntimeOperationResult | None = None
        try:
            context.assert_can_continue()
            self._assert_runtime_selection(context)
            context.emit("planning", "Deployment plan is being prepared.", progress=10)
            plan = strategy.plan(context)
            context.assert_can_continue()

            context.emit("runtime_apply", "Applying the deployment plan.", progress=45)
            applied = runtime.apply(plan, operation_key=context.operation("apply"))
            handle = applied.handle
            if handle is None:
                raise RuntimeOperationError(
                    "Runtime apply completed without returning a handle.",
                    code="runtime_handle_missing",
                )
            context.assert_can_continue()

            context.emit("readiness", "Waiting for runtime readiness.", progress=75)
            ready = runtime.wait_ready(
                handle,
                timeout=readiness_timeout,
                cancel_check=context.cancellation_requested,
            )
            context.assert_can_continue()

            strategy.activate(context, plan, ready)
            transitioned = self.store.transition(
                context,
                sm.DEPLOY_SUCCEEDED,
                message="Deployment completed successfully.",
                details={"runtime": context.runtime_selection.backend},
            )
            if not transitioned:
                return self._stale_result(context)
            if self.store.status != sm.DEPLOY_SUCCEEDED:
                # The terminal store may have won a cancellation race while
                # this worker was finishing activation.  Treat that result as
                # cancellation and clean up only while ownership is current.
                self._cancel_runtime(context, runtime, handle)
                cancelled = DeploymentCancelled(
                    "Deployment cancellation won the completion race.",
                    details={"deployment_id": context.deployment_id},
                )
                context.emit("cancelled", cancelled.user_message, level="warning", progress=100)
                return DeploymentLifecycleResult(
                    status=self.store.status,
                    success=False,
                    error=cancelled,
                    runtime_result=ready,
                    details=cancelled.details,
                )
            context.emit("deployment_completed", "Deployment completed successfully.", progress=100)
            return DeploymentLifecycleResult(
                status=self.store.status,
                success=True,
                runtime_result=ready,
            )
        except DeploymentCancelled as exc:
            return self._finish_cancellation(context, runtime, handle, exc)
        except StaleDeploymentWorkerError as exc:
            # A stale worker must not clean up or transition a resource that a
            # newer owner may already be using.
            return self._stale_result(context, error=exc)
        except Exception as exc:
            if isinstance(exc, RuntimeOperationError) and exc.code == "runtime_cancelled":
                return self._finish_cancellation(
                    context,
                    runtime,
                    handle,
                    DeploymentCancelled(exc.user_message, details=exc.details),
                )
            error = exc if isinstance(exc, DeploymentError) else to_deployment_error(exc, stage="deployment_execution")
            rollback_performed, rollback_failed = self._recover_failure(
                context,
                runtime,
                plan,
                handle,
            )
            transitioned = self.store.transition(
                context,
                sm.DEPLOY_FAILED,
                message=error.user_message,
                details={
                    **error.details,
                    "error_code": error.code,
                    "recoverable": error.recoverable,
                    "rollback_performed": rollback_performed,
                    "rollback_failed": rollback_failed,
                },
            )
            if not transitioned:
                return self._stale_result(context, error=error)
            context.emit(
                "deployment_failed",
                error.user_message,
                level="error",
                progress=100,
                details={"error_code": error.code, "recoverable": error.recoverable},
            )
            return DeploymentLifecycleResult(
                status=self.store.status,
                success=False,
                retryable=bool(error.recoverable),
                runtime_result=applied,
                error=error,
                rollback_performed=rollback_performed,
                rollback_failed=rollback_failed,
                details=error.details,
            )

    @staticmethod
    def _assert_runtime_selection(context: DeploymentExecutionContext) -> None:
        selection = context.runtime_selection
        missing = selection.missing_capabilities
        if missing:
            raise RuntimeUnsupportedError(
                "The selected runtime cannot satisfy this deployment.",
                details={"missing": sorted(value.value for value in missing)},
            )
        availability = selection.availability
        if not availability.operator_enabled:
            raise RuntimeUnavailableError(
                availability.message or "The selected runtime is disabled by operator policy.",
                code=(
                    availability.reason_code
                    if availability.reason_code not in {"", "availability_not_probed"}
                    else "runtime_disabled"
                ),
                details={"availability": availability.state.value},
            )
        if availability.state.value != "unknown" and not availability.can_execute:
            raise RuntimeUnavailableError(
                availability.message or "The selected runtime is unavailable.",
                code=availability.reason_code or "runtime_unavailable",
                details={"availability": availability.state.value},
            )

    def _finish_cancellation(
        self,
        context: DeploymentExecutionContext,
        runtime: RuntimeContract,
        handle: RuntimeHandle | None,
        error: DeploymentCancelled,
    ) -> DeploymentLifecycleResult:
        self._cancel_runtime(context, runtime, handle)
        transitioned = self.store.transition(
            context,
            sm.DEPLOY_CANCELLED,
            message=error.user_message,
            details=error.details,
        )
        if transitioned:
            context.emit("cancelled", error.user_message, level="warning", progress=100)
            return DeploymentLifecycleResult(
                status=self.store.status,
                success=False,
                error=error,
                details=error.details,
            )
        return self._stale_result(context, error=error)

    @staticmethod
    def _stale_result(
        context: DeploymentExecutionContext,
        *,
        error: DeploymentError | None = None,
    ) -> DeploymentLifecycleResult:
        return DeploymentLifecycleResult(
            status="stale",
            success=False,
            error=error,
            details={
                "deployment_id": context.deployment_id,
                "operation_key": context.operation_key,
            },
        )

    @staticmethod
    def _cancel_runtime(
        context: DeploymentExecutionContext,
        runtime: RuntimeContract,
        handle: RuntimeHandle | None,
    ) -> None:
        if handle is None or not context.owns_execution():
            return
        try:
            runtime.stop(handle, operation_key=context.operation("cancel-stop"))
            runtime.remove(handle, operation_key=context.operation("cancel-remove"))
        except Exception:
            return

    @staticmethod
    def _recover_failure(
        context: DeploymentExecutionContext,
        runtime: RuntimeContract,
        plan: Any,
        handle: RuntimeHandle | None,
    ) -> tuple[bool, bool]:
        if plan is None or handle is None or not context.owns_execution():
            return False, False
        target_plan = getattr(plan, "rollback_plan", None)
        if target_plan is None:
            return False, False
        try:
            runtime.rollback(
                plan,
                operation_key=context.operation("rollback"),
                target_plan=target_plan,
            )
            return True, False
        except Exception:
            return False, True
