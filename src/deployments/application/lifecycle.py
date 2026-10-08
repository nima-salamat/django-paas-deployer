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
from deployments.observability import deployment_span
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
    cleanup_performed: bool = False
    cleanup_failed: bool = False
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
        finalization: dict[str, Any] = {}
        try:
            context.assert_can_continue()
            self._assert_runtime_selection(context)
            context.emit("planning", "Deployment plan is being prepared.", progress=10)
            with deployment_span("revision.snapshot", attributes={"deployment.id": context.deployment_id, "service.id": context.service_id, "revision.id": context.revision_id}):
                plan = strategy.plan(context)
            context.assert_can_continue()

            context.emit("runtime_apply", "Applying the deployment plan.", progress=45)
            with deployment_span("runtime.apply", attributes={"deployment.id": context.deployment_id, "runtime.backend": runtime.backend}):
                applied = runtime.apply(
                    plan,
                    operation_key=context.operation("apply"),
                    cancel_check=context.cancellation_requested,
                )
            handle = applied.handle
            if handle is None:
                raise RuntimeOperationError(
                    "Runtime apply completed without returning a handle.",
                    code="runtime_handle_missing",
                )
            journal = getattr(self.store, "journal_runtime_resource", None)
            if callable(journal):
                service_names = tuple(handle.metadata.get("service_names") or ())
                service_ids = dict(handle.metadata.get("service_ids") or {})
                if not service_names:
                    service_names = (handle.resource_name or handle.identity.resource_name(),)
                for service_name in service_names:
                    journal(
                        context,
                        kind="runtime_service",
                        name=str(service_name),
                        runtime_id=str(service_ids.get(service_name) or handle.runtime_id or ""),
                        state="active",
                        metadata={
                            "operation_key": context.operation("apply"),
                            "revision_id": str(context.revision_id or ""),
                            "release_id": str(getattr(plan, "release_id", "") or ""),
                            "artifact_digest": str(getattr(plan, "artifact_digest", "") or ""),
                            "process": str(
                                service_name.rsplit("-", 1)[-1]
                                if service_name != handle.resource_name
                                else getattr(handle.identity, "process_name", "web")
                            ),
                        },
                    )
            context.assert_can_continue()

            context.emit("readiness", "Waiting for runtime readiness.", progress=75)
            with deployment_span("runtime.wait_ready", attributes={"deployment.id": context.deployment_id, "runtime.backend": runtime.backend}):
                ready = runtime.wait_ready(
                    handle,
                    timeout=readiness_timeout,
                    cancel_check=context.cancellation_requested,
                )
            context.assert_can_continue()

            # Runtime resources that existed only for the previous process graph
            # are safe to remove now: the new revision has passed readiness, but
            # the authoritative database activation has not committed yet. If
            # cleanup fails, normal rollback can restore the previous release.
            finalize = getattr(runtime, "finalize_success", None)
            if callable(finalize):
                finalization = dict(
                    finalize(
                        handle,
                        operation_key=context.operation("finalize"),
                        cancel_check=context.cancellation_requested,
                    )
                    or {}
                )
            context.assert_can_continue()

            with deployment_span("activation.commit", attributes={"deployment.id": context.deployment_id, "revision.id": context.revision_id}):
                strategy.activate(context, plan, ready)
            transitioned = self.store.transition(
                context,
                sm.DEPLOY_SUCCEEDED,
                message="Deployment completed successfully.",
                details={
                    "runtime": context.runtime_selection.backend,
                    **finalization,
                },
            )
            if not transitioned:
                return self._stale_result(context)
            if self.store.status != sm.DEPLOY_SUCCEEDED:
                # The terminal store may have won a cancellation race while
                # this worker was finishing activation.  Treat that result as
                # cancellation and clean up only while ownership is current.
                self._cancel_runtime(
                    context,
                    runtime,
                    handle,
                    rollback_plan=getattr(plan, "rollback_plan", None) if plan is not None else None,
                )
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
            return self._finish_cancellation(context, runtime, plan, handle, exc)
        except StaleDeploymentWorkerError as exc:
            # A stale worker must not clean up or transition a resource that a
            # newer owner may already be using.
            return self._stale_result(context, error=exc)
        except Exception as exc:
            if isinstance(exc, RuntimeOperationError) and exc.code == "runtime_cancelled":
                return self._finish_cancellation(
                    context,
                    runtime,
                    plan,
                    handle,
                    DeploymentCancelled(exc.user_message, details=exc.details),
                )
            error = exc if isinstance(exc, DeploymentError) else to_deployment_error(exc, stage="deployment_execution")
            rollback_performed, rollback_failed, cleanup_details = self._recover_failure(
                context,
                runtime,
                plan,
                handle,
                error.details,
            )
            cleanup_failed = bool(cleanup_details.get("cleanup_failed"))
            cleanup_performed = bool(cleanup_details.get("cleanup_attempted"))
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
                    "cleanup_performed": cleanup_performed,
                    "cleanup_failed": cleanup_failed,
                    "reconciliation_required": bool(rollback_failed or cleanup_failed),
                    **cleanup_details,
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
                cleanup_performed=cleanup_performed,
                cleanup_failed=cleanup_failed,
                details={
                    **dict(error.details or {}),
                    **cleanup_details,
                },
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
        plan: Any,
        handle: RuntimeHandle | None,
        error: DeploymentCancelled,
    ) -> DeploymentLifecycleResult:
        rollback_plan = getattr(plan, "rollback_plan", None) if plan is not None else None
        cleanup = self._cancel_runtime(
            context,
            runtime,
            handle,
            rollback_plan=rollback_plan,
            apply_failure_details=error.details,
        )
        details = {**dict(error.details or {}), **cleanup}
        transitioned = self.store.transition(
            context,
            sm.DEPLOY_CANCELLED,
            message=error.user_message,
            details=details,
        )
        if transitioned:
            context.emit(
                "cancelled",
                error.user_message,
                level="warning",
                progress=100,
                details=details,
            )
            return DeploymentLifecycleResult(
                status=self.store.status,
                success=False,
                error=error,
                details=details,
            )
        return self._stale_result(context, error=error)

    @staticmethod
    def _cancel_runtime(
        context: DeploymentExecutionContext,
        runtime: RuntimeContract,
        handle: RuntimeHandle | None,
        *,
        rollback_plan: Any | None = None,
        apply_failure_details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not context.owns_execution():
            return {}

        if handle is None:
            recovery = getattr(runtime, "recover_failed_apply", None)
            if callable(recovery) and apply_failure_details:
                return dict(
                    recovery(
                        dict(apply_failure_details),
                        operation_key=context.operation("cancel-recovery"),
                        cancel_check=lambda: False,
                    )
                    or {}
                )
            return {}

        # Replacement cancellation must restore the previously active release.
        # The Swarm backend updates the existing canonical service name in place;
        # stopping/removing that handle would therefore destroy production state.
        if rollback_plan is not None:
            try:
                runtime.rollback(
                    rollback_plan,
                    operation_key=context.operation("cancel-rollback"),
                    target_plan=rollback_plan,
                    cancel_check=lambda: False,
                )
                return {
                    "cleanup_failed": False,
                    "rollback_performed": True,
                    "cleanup_attempted": False,
                }
            except Exception as exc:
                return {
                    "cleanup_failed": True,
                    "reconciliation_required": True,
                    "rollback_failed": True,
                    "cleanup_attempted": False,
                    "cleanup_failures": [{
                        "operation": "rollback",
                        "error_code": str(getattr(exc, "code", "") or "runtime_rollback_failed"),
                        "error": str(getattr(exc, "technical_message", None) or exc),
                    }],
                }

        failures = []
        for action, suffix in (("stop", "cancel-stop"), ("remove", "cancel-remove")):
            try:
                operation = runtime.stop if action == "stop" else runtime.remove
                operation(
                    handle,
                    operation_key=context.operation(suffix),
                    cancel_check=lambda: False,
                )
            except Exception as exc:
                failures.append(
                    {
                        "operation": action,
                        "error_code": str(
                            getattr(exc, "code", "") or "runtime_cleanup_failed"
                        ),
                        "error": str(
                            getattr(exc, "technical_message", None) or exc
                        ),
                    }
                )
        if not failures:
            return {"cleanup_failed": False}
        return {
            "cleanup_failed": True,
            "reconciliation_required": True,
            "cleanup_failures": failures,
        }

    @staticmethod
    def _recover_failure(
        context: DeploymentExecutionContext,
        runtime: RuntimeContract,
        plan: Any,
        handle: RuntimeHandle | None,
        failure_details: Mapping[str, Any] | None = None,
    ) -> tuple[bool, bool, dict[str, Any]]:
        if not context.owns_execution():
            return False, False, {}

        if handle is None:
            recovery = getattr(runtime, "recover_failed_apply", None)
            if callable(recovery) and failure_details:
                try:
                    result = dict(
                        recovery(
                            dict(failure_details),
                            operation_key=context.operation("apply-recovery"),
                            cancel_check=lambda: False,
                        )
                        or {}
                    )
                    return (
                        False,
                        bool(result.get("rollback_failed")),
                        result,
                    )
                except Exception as exc:
                    return False, True, {
                        "cleanup_attempted": True,
                        "cleanup_failed": True,
                        "reconciliation_required": True,
                        "cleanup_failures": [{
                            "operation": "partial_apply_recovery",
                            "error": str(getattr(exc, "technical_message", None) or exc),
                        }],
                    }
            return False, False, {}

        target_plan = getattr(plan, "rollback_plan", None)
        if target_plan is not None:
            try:
                runtime.rollback(
                    plan,
                    operation_key=context.operation("rollback"),
                    target_plan=target_plan,
                    cancel_check=context.cancellation_requested,
                )
                return True, False, {"cleanup_attempted": False}
            except Exception as exc:
                return False, True, {
                    "cleanup_attempted": False,
                    "rollback_error": str(getattr(exc, "technical_message", None) or exc),
                    "reconciliation_required": True,
                }

        # Initial deployments have no previous release. If runtime.apply()
        # succeeded but readiness later fails, the new resource is still owned
        # by this deployment and must not be stranded in the runtime.
        cleanup = DeploymentLifecycleExecutor._cancel_runtime(context, runtime, handle)
        cleanup = {
            "cleanup_attempted": True,
            **dict(cleanup or {}),
        }
        return False, False, cleanup
