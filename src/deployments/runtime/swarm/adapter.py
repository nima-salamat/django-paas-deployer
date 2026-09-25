"""Compatibility adapter around the existing SwarmRuntime implementation.

This module intentionally delegates to deployments.core.swarm for now.  The
adapter is the migration seam; the Swarm implementation will be decomposed
only after callers use this contract.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from deployments.common.exceptions import DeploymentError
from deployments.core.swarm import SwarmRuntime, SwarmServiceState, swarm_enabled

from ..capabilities import (
    RuntimeAvailability,
    RuntimeAvailabilityState,
    RuntimeCapabilities,
    RuntimeCapability,
)
from ..contract import (
    RuntimeBackend,
    RuntimeContract,
    RuntimeHandle,
    RuntimeIdentity,
    RuntimeOperationResult,
)
from ..errors import RuntimeOperationError, RuntimeUnavailableError, RuntimeUnsupportedError
from ..observations import (
    RuntimeObservation,
    RuntimeObservedStatus,
    RuntimeTaskObservation,
)


class SwarmRuntimeAdapter:
    """Expose the current Swarm runtime through the runtime contract."""

    backend = RuntimeBackend.SWARM.value

    def __init__(
        self,
        *,
        runtime: SwarmRuntime | None = None,
        runtime_factory: Callable[[], SwarmRuntime] | None = None,
        operator_enabled: bool | None = None,
    ) -> None:
        self._runtime = runtime
        self._runtime_factory = runtime_factory or SwarmRuntime
        self._operator_enabled = operator_enabled

    @property
    def runtime(self) -> SwarmRuntime:
        if self._runtime is None:
            self._runtime = self._runtime_factory()
        return self._runtime

    def describe_capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            backend=self.backend,
            supported=frozenset(
                {
                    RuntimeCapability.SERVICE_SCHEDULING,
                    RuntimeCapability.REPLICAS,
                    RuntimeCapability.ROLLING_UPDATE,
                    RuntimeCapability.ROLLBACK,
                    RuntimeCapability.NODE_CONSTRAINTS,
                    RuntimeCapability.OVERLAY_NETWORKS,
                    RuntimeCapability.PERSISTENT_VOLUMES,
                    RuntimeCapability.SERVICE_LOGS,
                    RuntimeCapability.HEALTH_CHECKS,
                    RuntimeCapability.PROCESS_GRAPH,
                }
            ),
            metadata={"replica_limit": "0..1", "adapter": "legacy-swarm-runtime"},
        )

    def check_availability(
        self, *, operator_enabled: bool | None = None
    ) -> RuntimeAvailability:
        enabled = (
            self._operator_enabled
            if operator_enabled is None and self._operator_enabled is not None
            else operator_enabled
        )
        if enabled is None:
            enabled = swarm_enabled()
        if not enabled:
            return RuntimeAvailability(
                backend=self.backend,
                state=RuntimeAvailabilityState.DISABLED,
                operator_enabled=False,
                reason_code="runtime_disabled",
                message="Docker Swarm runtime is disabled by operator/bootstrap policy.",
            )
        try:
            swarm = self.runtime.assert_active()
        except DeploymentError as exc:
            code = str(getattr(exc, "code", "") or "runtime_unavailable")
            if code == "SWARM_DISABLED":
                state = RuntimeAvailabilityState.DISABLED
                reachable = False
                manager = False
            elif code == "DOCKER_UNAVAILABLE":
                state = RuntimeAvailabilityState.UNAVAILABLE
                reachable = False
                manager = False
            elif code in {"SWARM_NOT_ACTIVE", "SWARM_NOT_MANAGER"}:
                state = RuntimeAvailabilityState.DEGRADED
                reachable = True
                manager = code != "SWARM_NOT_MANAGER"
            else:
                state = RuntimeAvailabilityState.UNAVAILABLE
                reachable = False
                manager = False
            return RuntimeAvailability(
                backend=self.backend,
                state=state,
                operator_enabled=True,
                reachable=reachable,
                manager_capable=manager,
                reason_code=code.lower(),
                message=str(getattr(exc, "user_message", None) or exc),
                details=getattr(exc, "details", {}) or {},
            )
        except Exception as exc:  # Docker SDK versions may expose other errors.
            return RuntimeAvailability(
                backend=self.backend,
                state=RuntimeAvailabilityState.UNAVAILABLE,
                operator_enabled=True,
                reason_code="runtime_probe_failed",
                message=str(exc),
            )
        return RuntimeAvailability(
            backend=self.backend,
            state=RuntimeAvailabilityState.ACTIVE,
            operator_enabled=True,
            reachable=True,
            manager_capable=bool((swarm or {}).get("ControlAvailable")),
            reason_code="",
            message="Docker Swarm manager is active.",
            details={"local_node_state": (swarm or {}).get("LocalNodeState")},
        )

    @staticmethod
    def _identity(plan: Any) -> RuntimeIdentity:
        value = getattr(plan, "identity", plan)
        if isinstance(value, RuntimeIdentity):
            return value
        return RuntimeIdentity(
            service_id=str(getattr(value, "service_id", "service")),
            deployment_id=getattr(value, "deployment_id", None),
            revision_id=getattr(value, "revision_id", None),
            process_name=str(getattr(value, "process_name", "web")),
            runtime_name=str(getattr(value, "runtime_name", "") or ""),
        )

    @staticmethod
    def _plan_config(plan: Any) -> tuple[Any, str]:
        config = getattr(plan, "deployment_config", None)
        image_ref = getattr(plan, "image_ref", None)
        if config is None:
            config = getattr(plan, "config", None)
        if image_ref is None and config is not None:
            image_ref = getattr(config, "image_ref", None)
        if config is None or not image_ref:
            raise RuntimeOperationError(
                "The Swarm compatibility adapter requires a compiled deployment config and image reference.",
                code="swarm_plan_bridge_required",
                category="runtime_contract",
            )
        return config, str(image_ref)

    @staticmethod
    def _ensure_available(adapter: "SwarmRuntimeAdapter") -> None:
        availability = adapter.check_availability()
        if not availability.can_execute:
            if availability.state == RuntimeAvailabilityState.DISABLED:
                raise RuntimeUnavailableError(
                    availability.message,
                    code="runtime_disabled",
                    recoverable=False,
                )
            raise RuntimeUnavailableError(
                availability.message or "Docker Swarm is unavailable.",
                code=availability.reason_code or "runtime_unavailable",
                details=availability.details,
            )

    def apply(self, plan: Any, *, operation_key: str) -> RuntimeOperationResult:
        self._ensure_available(self)
        config, image_ref = self._plan_config(plan)
        identity = self._identity(plan)
        try:
            state = self.runtime.apply(config, image_ref=image_ref)
        except DeploymentError as exc:
            raise RuntimeOperationError(
                str(exc),
                code=str(getattr(exc, "code", "swarm_apply_failed") or "swarm_apply_failed").lower(),
                recoverable=bool(getattr(exc, "recoverable", False)),
                category=str(getattr(exc, "category", "runtime_error") or "runtime_error"),
                details=getattr(exc, "details", {}) or {},
                user_message=getattr(exc, "user_message", None),
            ) from exc
        observation = self._observation(identity, state, assume_identity_revision=True)
        handle = RuntimeHandle(
            backend=self.backend,
            identity=identity,
            runtime_id=observation.runtime_id,
            resource_name=identity.resource_name(),
        )
        return RuntimeOperationResult(
            success=True,
            changed=True,
            handle=handle,
            observation=observation,
            details={"operation_key": operation_key},
        )

    def inspect(self, identity: RuntimeIdentity) -> RuntimeObservation:
        self._ensure_available(self)
        try:
            state = self.runtime.inspect_service(identity.resource_name())
        except DeploymentError as exc:
            raise RuntimeOperationError(
                str(exc),
                code=str(getattr(exc, "code", "swarm_inspect_failed") or "swarm_inspect_failed").lower(),
                recoverable=bool(getattr(exc, "recoverable", False)),
            ) from exc
        # Inspection is observed state, not desired state. If an externally
        # created service has no managed revision label, keep the revision
        # unknown so reconciliation can request operator intervention instead
        # of silently declaring it converged.
        return self._observation(identity, state, assume_identity_revision=False)

    def wait_ready(
        self,
        handle: RuntimeHandle,
        *,
        timeout: float | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> RuntimeOperationResult:
        self._ensure_available(self)
        if cancel_check is not None and cancel_check():
            raise RuntimeOperationError(
                "Runtime readiness was cancelled.",
                code="runtime_cancelled",
                category="cancellation",
            )
        try:
            state = self.runtime.wait_ready(
                handle.resource_name or handle.identity.resource_name(),
                timeout=float(timeout or 60),
            )
        except DeploymentError as exc:
            raise RuntimeOperationError(
                str(exc),
                code=str(getattr(exc, "code", "swarm_readiness_failed") or "swarm_readiness_failed").lower(),
                recoverable=bool(getattr(exc, "recoverable", False)),
                details=getattr(exc, "details", {}) or {},
                user_message=getattr(exc, "user_message", None),
            ) from exc
        observation = self._observation(handle.identity, state, assume_identity_revision=True)
        return RuntimeOperationResult(success=True, changed=True, handle=handle, observation=observation)

    def stop(self, handle: RuntimeHandle, *, operation_key: str) -> RuntimeOperationResult:
        self._ensure_available(self)
        self.runtime.stop(handle.resource_name or handle.identity.resource_name())
        return RuntimeOperationResult(success=True, changed=True, handle=handle, details={"operation_key": operation_key})

    def remove(self, handle: RuntimeHandle, *, operation_key: str) -> RuntimeOperationResult:
        self._ensure_available(self)
        self.runtime.remove(handle.resource_name or handle.identity.resource_name())
        return RuntimeOperationResult(success=True, changed=True, handle=handle, details={"operation_key": operation_key})

    def rollback(
        self,
        plan: Any,
        *,
        operation_key: str,
        target_plan: Any | None = None,
    ) -> RuntimeOperationResult:
        rollback_plan = target_plan or getattr(plan, "rollback_plan", None)
        if rollback_plan is None:
            raise RuntimeUnsupportedError(
                "Swarm rollback requires an explicit previously-known-good plan.",
                code="swarm_rollback_plan_required",
            )
        return self.apply(rollback_plan, operation_key=operation_key)

    def logs(self, identity: RuntimeIdentity, *, tail: int | str = 200) -> Any:
        self._ensure_available(self)
        return self.runtime.service_logs(identity.resource_name(), tail=tail)

    @staticmethod
    def _observation(
        identity: RuntimeIdentity,
        state: SwarmServiceState | None,
        *,
        assume_identity_revision: bool = False,
    ) -> RuntimeObservation:
        if state is None:
            return RuntimeObservation(identity=identity, status=RuntimeObservedStatus.MISSING)
        tasks = tuple(
            RuntimeTaskObservation(
                task_id=item.task_id,
                desired_state=item.desired_state,
                state=item.state,
                node_id=item.node_id,
                node_name=item.node_name,
                error=item.error,
                message=item.message,
            )
            for item in state.tasks
        )
        ready = state.replicas_desired == state.replicas_running and state.replicas_running > 0
        status = RuntimeObservedStatus.READY if ready else RuntimeObservedStatus.DEGRADED
        labels = dict(state.labels or {})
        observed_revision = (
            labels.get("revision.id")
            or labels.get("passdeployer.revision")
            or (identity.revision_id if assume_identity_revision else None)
        )
        return RuntimeObservation(
            identity=replace(identity, revision_id=observed_revision),
            status=status,
            runtime_id=state.service_id,
            desired_replicas=state.replicas_desired,
            ready_replicas=state.replicas_running,
            tasks=tasks,
            details={"service_name": state.name, "labels": labels},
        )
