"""Common deployment lifecycle executor.

The executor owns lifecycle sequencing and fencing.  A strategy owns how a
plan is built and activated; a runtime adapter owns external runtime calls.
Neither application nor database strategy needs to duplicate this state
machine.
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

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
        self.last_activation_outcome: str | None = None

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
        self.last_activation_outcome = None
        if target == sm.DEPLOY_SUCCEEDED:
            if context.cancellation_requested():
                self.last_activation_outcome = "cancelled"
                return False
            self.last_activation_outcome = "activated"
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
            contract_details = {}
            contracts = dict(getattr(plan, "execution_contracts", {}) or {})
            if contracts:
                contract_details = {
                    "execution_contracts": {
                        name: contract.as_dict()
                        for name, contract in contracts.items()
                    },
                    "execution_contract_hashes": dict(
                        getattr(plan, "runtime_options", {}).get("execution_contract_hashes") or {}
                    ),
                    "deployment_provenance": dict(
                        getattr(plan, "runtime_options", {}).get("deployment_provenance") or {}
                    ),
                }
            context.emit(
                "runtime_contract",
                "Runtime execution contract resolved from the immutable revision.",
                progress=30,
                details=contract_details,
            )

            context.emit("runtime_apply", "Applying the deployment plan.", progress=45)
            self._journal_plan_resources(context, plan, state="planned")
            with deployment_span("runtime.apply", attributes={"deployment.id": context.deployment_id, "runtime.backend": runtime.backend}):
                applied = runtime.apply(
                    plan,
                    operation_key=context.operation("apply"),
                    cancel_check=context.runtime_cancel_check,
                )
            handle = applied.handle
            if handle is None:
                raise RuntimeOperationError(
                    "Runtime apply completed without returning a handle.",
                    code="runtime_handle_missing",
                )
            self._journal_plan_resources(
                context,
                plan,
                state="created",
                handle=handle,
            )
            context.assert_can_continue()

            context.emit("readiness", "Waiting for runtime readiness.", progress=75)
            with deployment_span("runtime.wait_ready", attributes={"deployment.id": context.deployment_id, "runtime.backend": runtime.backend}):
                ready = runtime.wait_ready(
                    handle,
                    timeout=readiness_timeout,
                    cancel_check=context.runtime_cancel_check,
                )
            context.assert_can_continue()
            self._journal_plan_resources(
                context,
                plan,
                state="ready",
                handle=handle,
            )

            # Activation is the authority boundary. Do not destructively clean
            # previous-process resources before activation: a failed activation
            # must still be able to restore the previous release completely.
            with deployment_span("activation.commit", attributes={"deployment.id": context.deployment_id, "revision.id": context.revision_id}):
                strategy.activate(context, plan, ready)
            transitioned = self.store.transition(
                context,
                sm.DEPLOY_SUCCEEDED,
                message="Deployment completed successfully.",
                details={
                    "runtime": context.runtime_selection.backend,
                },
            )
            if not transitioned:
                activation_outcome = getattr(self.store, "last_activation_outcome", None)
                if activation_outcome == "cancelled":
                    return self._finish_cancellation(
                        context,
                        runtime,
                        plan,
                        handle,
                        DeploymentCancelled(
                            "Deployment cancellation won immediately before activation.",
                            stage="cancelled",
                            user_message="Deployment cancelled by the user.",
                            details={
                                "deployment_id": context.deployment_id,
                                "activation_outcome": "cancelled",
                            },
                        ),
                    )
                if activation_outcome == "activation_conflict":
                    raise DeploymentError(
                        "The active revision changed before this deployment could be committed.",
                        code="deployment_activation_conflict",
                        stage="activation",
                        recoverable=False,
                        user_message=(
                            "The deployment finished starting, but a newer lifecycle change "
                            "won the activation race. Runtime reconciliation was requested."
                        ),
                        details={
                            "activation_outcome": activation_outcome,
                            "reconciliation_required": True,
                            "revision_id": str(context.revision_id or ""),
                        },
                    )
                return self._stale_result(context, runtime_result=ready)

            finalization: dict[str, Any] = {}
            try:
                self._journal_plan_resources(
                    context,
                    plan,
                    state="active",
                    handle=handle,
                )
            except Exception:
                # Activation and its terminal outbox are already durable. A
                # journal projection failure must be recovered from runtime labels.
                finalization["reconciliation_required"] = True
                finalization["journal_update_failed"] = True
                logger.exception(
                    "Could not mark runtime journal active for deployment %s.",
                    context.deployment_id,
                )

            # Cleanup is deliberately post-activation. A cleanup failure must
            # never turn an already-activated deployment into FAILED; instead
            # record reconciliation-required state and let the runtime monitor
            # converge the stale resource later.
            finalize = getattr(runtime, "finalize_success", None)
            if callable(finalize):
                try:
                    runtime_finalization = dict(finalize(
                        handle,
                        operation_key=context.operation("finalize"),
                        cancel_check=context.runtime_cancel_check,
                    ) or {})
                    finalization = {
                        **finalization,
                        **runtime_finalization,
                    }
                    if finalization.get("journal_update_failed"):
                        finalization["reconciliation_required"] = True
                except Exception as finalize_exc:
                    finalization = {
                        **finalization,
                        "cleanup_attempted": True,
                        "cleanup_failed": True,
                        "reconciliation_required": True,
                        "cleanup_failures": [{
                            "operation": "post_activation_cleanup",
                            "error": str(
                                getattr(finalize_exc, "technical_message", None)
                                or finalize_exc
                            ),
                        }],
                    }
                    context.emit(
                        "runtime_cleanup_degraded",
                        "Deployment activated successfully, but old runtime resources still require cleanup.",
                        level="warning",
                        progress=100,
                        details=finalization,
                    )
            record_finalization = getattr(self.store, "record_finalization", None)
            if callable(record_finalization):
                try:
                    record_finalization(context, finalization)
                except Exception:
                    logger.exception(
                        "Could not persist post-activation cleanup result for deployment %s.",
                        context.deployment_id,
                    )
            if self.store.status != sm.DEPLOY_SUCCEEDED:
                context.assert_can_continue()
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
                cleanup_performed=bool(finalization.get("cleanup_attempted")),
                cleanup_failed=bool(finalization.get("cleanup_failed")),
                details=finalization,
            )
        except DeploymentCancelled as exc:
            return self._finish_cancellation(context, runtime, plan, handle, exc)
        except StaleDeploymentWorkerError as exc:
            # A stale worker must not clean up or transition a resource that a
            # newer owner may already be using.
            return self._stale_result(context, error=exc, runtime_result=applied)
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
            activation_conflict = error.code == "deployment_activation_conflict"
            if activation_conflict:
                # The Runtime may now be shared with a newer authoritative
                # revision. Leave it untouched and let reconciliation converge
                # to Service.active_revision.
                rollback_performed, rollback_failed, cleanup_details = (
                    False,
                    False,
                    {"reconciliation_required": True, "cleanup_attempted": False},
                )
            else:
                rollback_performed, rollback_failed, cleanup_details = self._recover_failure(
                    context,
                    runtime,
                    plan,
                    handle,
                    error.details,
                    readiness_timeout=readiness_timeout,
                )
            cleanup_failed = bool(cleanup_details.get("cleanup_failed"))
            cleanup_performed = bool(cleanup_details.get("cleanup_attempted"))
            try:
                self._journal_plan_resources(
                    context,
                    plan,
                    state=(
                        "cleanup_pending"
                        if cleanup_failed or activation_conflict
                        else "retired"
                    ),
                    handle=handle,
                    error=str(error.technical_message or error),
                )
            except Exception:
                logger.exception(
                    "Could not persist failed runtime resource journal for deployment %s.",
                    context.deployment_id,
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
                    "cleanup_performed": cleanup_performed,
                    "cleanup_failed": cleanup_failed,
                    "reconciliation_required": bool(
                        activation_conflict or rollback_failed or cleanup_failed
                    ),
                    **cleanup_details,
                },
            )
            if not transitioned:
                return self._stale_result(context, error=error, runtime_result=applied)
            if self.store.status == sm.DEPLOY_CANCELLED:
                cancelled_error = DeploymentCancelled(
                    "Deployment cancellation won the retry transition race.",
                    stage="cancelled",
                    user_message="Deployment cancelled by the user.",
                    details={
                        **dict(error.details or {}),
                        **cleanup_details,
                        "cancellation_won_retry_race": True,
                    },
                )
                context.emit(
                    "cancelled",
                    cancelled_error.user_message,
                    level="warning",
                    progress=100,
                    details=cancelled_error.details,
                )
                return DeploymentLifecycleResult(
                    status=sm.DEPLOY_CANCELLED,
                    success=False,
                    retryable=False,
                    runtime_result=applied,
                    error=cancelled_error,
                    rollback_performed=rollback_performed,
                    rollback_failed=rollback_failed,
                    cleanup_performed=cleanup_performed,
                    cleanup_failed=cleanup_failed,
                    details=cancelled_error.details,
                )
            if error.recoverable and self.store.status == sm.DEPLOY_RUNNING:
                context.emit(
                    "retry_waiting",
                    "A temporary runtime failure occurred; the deployment attempt remains owned and will be retried.",
                    level="warning",
                    progress=85,
                    details={"error_code": error.code, "recoverable": True},
                )
            else:
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

    def _stale_result(
        self,
        context: DeploymentExecutionContext,
        *,
        error: DeploymentError | None = None,
        runtime_result: RuntimeOperationResult | None = None,
    ) -> DeploymentLifecycleResult:
        """Return a safe result when this worker no longer owns the lifecycle.

        A concurrent delivery can lose the final compare-and-set after another
        worker has already committed this Deploy as succeeded. In that case,
        the durable terminal row is authoritative: report the existing success
        without running cleanup or writing state again. Otherwise, leave all
        runtime/state mutation to the current owner.
        """
        observed_status = str(self.store.status or "")
        details = {
            "deployment_id": str(context.deployment_id),
            "service_id": str(context.service_id),
            "revision_id": str(context.revision_id or ""),
            "worker_task_id": str(context.worker_task_id or ""),
            "operation_key": str(context.operation_key),
            "observed_status": observed_status,
            "worker_ownership_lost": True,
        }
        if observed_status == sm.DEPLOY_SUCCEEDED:
            details["completion_already_committed"] = True
            return DeploymentLifecycleResult(
                status=sm.DEPLOY_SUCCEEDED,
                success=True,
                runtime_result=runtime_result,
                details=details,
            )

        if observed_status == sm.DEPLOY_CANCELLED:
            details["terminal_result_already_committed"] = True
            cancelled_error = (
                error
                if isinstance(error, DeploymentCancelled)
                else DeploymentCancelled(
                    "Deployment cancellation was already committed by the lifecycle owner.",
                    details=details,
                )
            )
            return DeploymentLifecycleResult(
                status=sm.DEPLOY_CANCELLED,
                success=False,
                runtime_result=runtime_result,
                error=cancelled_error,
                details={**details, **dict(cancelled_error.details or {})},
            )

        stale_error = error or StaleDeploymentWorkerError(
            "Deployment execution ownership is no longer current.",
            details=details,
        )
        if sm.is_deploy_terminal(observed_status):
            details["terminal_result_already_committed"] = True
            return DeploymentLifecycleResult(
                status=observed_status,
                success=False,
                runtime_result=runtime_result,
                error=stale_error,
                details={**details, **dict(stale_error.details or {})},
            )
        return DeploymentLifecycleResult(
            status="stale",
            success=False,
            runtime_result=runtime_result,
            error=stale_error,
            details={**details, **dict(stale_error.details or {})},
        )

    def _journal_plan_resources(
        self,
        context: DeploymentExecutionContext,
        plan: Any,
        *,
        state: str,
        handle: RuntimeHandle | None = None,
        error: str = "",
    ) -> None:
        journal = getattr(self.store, "journal_runtime_resource", None)
        if not callable(journal) or plan is None:
            return
        identity = getattr(plan, "identity", None)
        name_factory = getattr(identity, "resource_name", None)
        base_name = str(name_factory() if callable(name_factory) else "").strip()
        if not base_name:
            return
        runtime_options = dict(getattr(plan, "runtime_options", {}) or {})
        process_specs = list(runtime_options.get("processes") or ())
        if not process_specs:
            process_specs = [{"name": "web", "enabled": True}]
        metadata = dict(handle.metadata if handle is not None else {})
        service_ids = dict(metadata.get("service_ids") or {})
        known_names = set(metadata.get("service_names") or ())
        for item in process_specs:
            if not isinstance(item, Mapping) or item.get("enabled", True) is False:
                continue
            process_name = str(item.get("name") or "web").strip().lower()
            resource_name = (
                base_name if process_name == "web" else f"{base_name}-{process_name}"
            )
            if known_names and resource_name not in known_names:
                continue
            journal(
                context,
                kind="runtime_service",
                name=resource_name,
                runtime_id=str(
                    service_ids.get(resource_name)
                    or (metadata.get("runtime_id", "") if resource_name == base_name else "")
                    or (handle.runtime_id if handle is not None and resource_name == base_name else "")
                ),
                state=state,
                metadata={
                    "operation_key": context.operation("apply"),
                    "deployment_id": str(context.deployment_id),
                    "service_id": str(context.service_id),
                    "revision_id": str(context.revision_id or ""),
                    "release_id": str(getattr(plan, "release_id", "") or ""),
                    "artifact_digest": str(getattr(plan, "artifact_digest", "") or ""),
                    "process": process_name,
                    "ownership_label": "passdeployer.deployment",
                    "last_error": str(error or "")[:1000],
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
        try:
            self._journal_plan_resources(
                context,
                plan,
                state=("cleanup_pending" if cleanup.get("cleanup_failed") else "retired"),
                handle=handle,
                error=str(error.technical_message or error),
            )
        except Exception:
            logger.exception(
                "Could not persist cancelled runtime resource journal for deployment %s.",
                context.deployment_id,
            )
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
        readiness_timeout: float | None = None,
    ) -> dict[str, Any]:
        try:
            context.assert_owner()
        except StaleDeploymentWorkerError:
            return {}

        if handle is None:
            recovery = getattr(runtime, "recover_failed_apply", None)
            if callable(recovery) and apply_failure_details:
                try:
                    return dict(
                        recovery(
                            dict(apply_failure_details),
                            operation_key=context.operation("cancel-recovery"),
                            cancel_check=context.runtime_fence_check,
                        )
                        or {}
                    )
                except Exception as exc:
                    return {
                        "cleanup_attempted": True,
                        "cleanup_failed": True,
                        "reconciliation_required": True,
                        "cleanup_failures": [{
                            "operation": "partial_apply_recovery",
                            "error": str(getattr(exc, "technical_message", None) or exc),
                        }],
                    }
            return {}

        # Replacement cancellation must restore the previously active release.
        # The Swarm backend updates the existing canonical service name in place;
        # stopping/removing that handle would therefore destroy production state.
        if rollback_plan is not None:
            try:
                rollback_result = runtime.rollback(
                    rollback_plan,
                    operation_key=context.operation("cancel-rollback"),
                    target_plan=rollback_plan,
                    cancel_check=context.runtime_fence_check,
                )
                if not rollback_result.success or rollback_result.handle is None:
                    raise RuntimeOperationError(
                        "The previous runtime was not restored with an identifiable handle.",
                        code="deployment_rollback_unconfirmed",
                    )
                rollback_timeout = max(30.0, float(readiness_timeout or 0.0))
                readiness = runtime.wait_ready(
                    rollback_result.handle,
                    timeout=rollback_timeout,
                    cancel_check=context.runtime_fence_check,
                )
                if not readiness.success:
                    raise RuntimeOperationError(
                        "The previous runtime did not become ready after rollback.",
                        code="deployment_rollback_unready",
                    )
                return {
                    "cleanup_failed": False,
                    "rollback_performed": True,
                    "rollback_ready": True,
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
                    cancel_check=context.runtime_fence_check,
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
        *,
        readiness_timeout: float | None = None,
    ) -> tuple[bool, bool, dict[str, Any]]:
        try:
            context.assert_owner()
        except StaleDeploymentWorkerError:
            return False, False, {}

        if handle is None:
            recovery = getattr(runtime, "recover_failed_apply", None)
            if callable(recovery) and failure_details:
                try:
                    result = dict(
                        recovery(
                            dict(failure_details),
                            operation_key=context.operation("apply-recovery"),
                            cancel_check=context.runtime_fence_check,
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
                rollback_result = runtime.rollback(
                    plan,
                    operation_key=context.operation("rollback"),
                    target_plan=target_plan,
                    cancel_check=context.runtime_fence_check,
                )
                if not rollback_result.success or rollback_result.handle is None:
                    raise RuntimeOperationError(
                        "The previous runtime was not restored with an identifiable handle.",
                        code="deployment_rollback_unconfirmed",
                    )
                rollback_timeout = max(30.0, float(readiness_timeout or 0.0))
                readiness = runtime.wait_ready(
                    rollback_result.handle,
                    timeout=rollback_timeout,
                    cancel_check=context.runtime_fence_check,
                )
                if not readiness.success:
                    raise RuntimeOperationError(
                        "The previous runtime did not become ready after rollback.",
                        code="deployment_rollback_unready",
                    )
                return True, False, {
                    "cleanup_attempted": False,
                    "rollback_ready": True,
                }
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
