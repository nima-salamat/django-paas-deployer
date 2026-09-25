"""Deterministic in-memory runtime used by contract and application tests."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from .capabilities import (
    RuntimeAvailability,
    RuntimeAvailabilityState,
    RuntimeCapabilities,
    RuntimeCapability,
    capability_set,
)
from .contract import (
    RuntimeBackend,
    RuntimeContract,
    RuntimeHandle,
    RuntimeIdentity,
    RuntimeOperationResult,
)
from .errors import RuntimeOperationError, RuntimeUnavailableError, RuntimeUnsupportedError
from .observations import RuntimeObservation, RuntimeObservedStatus


class FakeRuntime:
    """Small runtime with explicit failure controls and idempotent operations."""

    backend = RuntimeBackend.SWARM.value

    def __init__(
        self,
        *,
        supported: set[RuntimeCapability] | None = None,
        operator_enabled: bool = True,
        reachable: bool = True,
        manager_capable: bool = True,
    ) -> None:
        self._supported = frozenset(
            supported
            if supported is not None
            else {
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
        )
        self.operator_enabled = bool(operator_enabled)
        self.reachable = bool(reachable)
        self.manager_capable = bool(manager_capable)
        self._observations: dict[str, RuntimeObservation] = {}
        self._snapshots: dict[str, RuntimeObservation | None] = {}
        self._operations: dict[str, RuntimeOperationResult] = {}
        self._logs: dict[str, list[str]] = {}
        self._readiness_errors: dict[str, RuntimeOperationError] = {}
        self.apply_count = 0
        self.stop_count = 0
        self.remove_count = 0

    def describe_capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(backend=self.backend, supported=self._supported)

    def check_availability(
        self, *, operator_enabled: bool | None = None
    ) -> RuntimeAvailability:
        enabled = self.operator_enabled if operator_enabled is None else bool(operator_enabled)
        if not enabled:
            state = RuntimeAvailabilityState.DISABLED
            reason = "runtime_disabled"
            message = "The runtime is disabled by operator policy."
        elif not self.reachable:
            state = RuntimeAvailabilityState.UNAVAILABLE
            reason = "runtime_unreachable"
            message = "The runtime is not reachable."
        elif not self.manager_capable:
            state = RuntimeAvailabilityState.DEGRADED
            reason = "runtime_not_manager_capable"
            message = "The runtime is reachable but cannot perform manager operations."
        else:
            state = RuntimeAvailabilityState.ACTIVE
            reason = ""
            message = ""
        return RuntimeAvailability(
            backend=self.backend,
            state=state,
            operator_enabled=enabled,
            reachable=self.reachable,
            manager_capable=self.manager_capable,
            reason_code=reason,
            message=message,
        )

    def _ensure_usable(self, plan: Any = None) -> None:
        availability = self.check_availability()
        if not availability.can_execute:
            raise RuntimeUnavailableError(
                availability.message or "The runtime is unavailable.",
                code=availability.reason_code or "runtime_unavailable",
                details={"availability": availability.state.value},
            )
        required = getattr(plan, "required_capabilities", ()) if plan is not None else ()
        missing = self.describe_capabilities().missing(*capability_set(required))
        if missing:
            raise RuntimeUnsupportedError(
                "The runtime does not support the requested capabilities.",
                details={"missing": sorted(value.value for value in missing)},
            )

    @staticmethod
    def _identity(value: Any) -> RuntimeIdentity:
        identity = getattr(value, "identity", value)
        if isinstance(identity, RuntimeIdentity):
            return identity
        return RuntimeIdentity(
            service_id=str(getattr(identity, "service_id", "service")),
            deployment_id=getattr(identity, "deployment_id", None),
            revision_id=getattr(identity, "revision_id", None),
            process_name=str(getattr(identity, "process_name", "web")),
            runtime_name=str(getattr(identity, "runtime_name", "") or ""),
        )

    def apply(self, plan: Any, *, operation_key: str) -> RuntimeOperationResult:
        self._ensure_usable(plan)
        if operation_key in self._operations:
            return replace(self._operations[operation_key], idempotent=True, changed=False)

        identity = self._identity(plan)
        key = identity.resource_name()
        self._snapshots[key] = self._observations.get(key)
        observation = RuntimeObservation(
            identity=identity,
            status=RuntimeObservedStatus.PROVISIONING,
            runtime_id=f"fake-{key}",
            desired_replicas=1,
            ready_replicas=0,
            revision_id=identity.revision_id,
        )
        self._observations[key] = observation
        self.apply_count += 1
        handle = RuntimeHandle(
            backend=self.backend,
            identity=identity,
            runtime_id=observation.runtime_id,
            resource_name=key,
        )
        result = RuntimeOperationResult(
            success=True,
            changed=True,
            handle=handle,
            observation=observation,
        )
        self._operations[operation_key] = result
        return result

    def inspect(self, identity: RuntimeIdentity) -> RuntimeObservation:
        current = self._observations.get(identity.resource_name())
        if current is not None:
            return current
        return RuntimeObservation(identity=identity, status=RuntimeObservedStatus.MISSING)

    def wait_ready(
        self,
        handle: RuntimeHandle,
        *,
        timeout: float | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> RuntimeOperationResult:
        self._ensure_usable()
        if cancel_check is not None and cancel_check():
            raise RuntimeOperationError(
                "Runtime readiness was cancelled.",
                code="runtime_cancelled",
                category="cancellation",
            )
        key = handle.identity.resource_name()
        error = self._readiness_errors.get(key)
        if error is not None:
            raise error
        current = self._observations.get(key)
        if current is None:
            raise RuntimeOperationError(
                "The runtime resource disappeared before readiness.",
                code="runtime_resource_missing",
                recoverable=True,
            )
        ready = replace(
            current,
            status=RuntimeObservedStatus.READY,
            desired_replicas=1,
            ready_replicas=1,
        )
        self._observations[key] = ready
        return RuntimeOperationResult(success=True, changed=True, handle=handle, observation=ready)

    def stop(self, handle: RuntimeHandle, *, operation_key: str) -> RuntimeOperationResult:
        self._ensure_usable()
        key = handle.identity.resource_name()
        current = self._observations.get(key)
        if current is None or current.status == RuntimeObservedStatus.STOPPED:
            return RuntimeOperationResult(success=True, idempotent=True, handle=handle, observation=current)
        stopped = replace(current, status=RuntimeObservedStatus.STOPPED, ready_replicas=0)
        self._observations[key] = stopped
        self.stop_count += 1
        return RuntimeOperationResult(success=True, changed=True, handle=handle, observation=stopped)

    def remove(self, handle: RuntimeHandle, *, operation_key: str) -> RuntimeOperationResult:
        self._ensure_usable()
        key = handle.identity.resource_name()
        current = self._observations.pop(key, None)
        self.remove_count += 1 if current is not None else 0
        missing = RuntimeObservation(identity=handle.identity, status=RuntimeObservedStatus.MISSING)
        return RuntimeOperationResult(
            success=True,
            changed=current is not None,
            idempotent=current is None,
            handle=handle,
            observation=missing,
        )

    def rollback(
        self,
        plan: Any,
        *,
        operation_key: str,
        target_plan: Any | None = None,
    ) -> RuntimeOperationResult:
        self._ensure_usable(plan)
        identity = self._identity(target_plan or plan)
        key = identity.resource_name()
        previous = self._snapshots.get(key)
        if previous is None:
            return self.remove(
                RuntimeHandle(backend=self.backend, identity=identity, resource_name=key),
                operation_key=operation_key,
            )
        self._observations[key] = previous
        handle = RuntimeHandle(
            backend=self.backend,
            identity=previous.identity,
            runtime_id=previous.runtime_id,
            resource_name=key,
        )
        return RuntimeOperationResult(
            success=True,
            changed=True,
            handle=handle,
            observation=previous,
        )

    def logs(self, identity: RuntimeIdentity, *, tail: int | str = 200) -> list[str]:
        rows = list(self._logs.get(identity.resource_name(), []))
        if isinstance(tail, int):
            return rows[-tail:]
        return rows

    def set_logs(self, identity: RuntimeIdentity, lines: list[str]) -> None:
        self._logs[identity.resource_name()] = list(lines)

    def set_readiness_error(self, identity: RuntimeIdentity, error: RuntimeOperationError) -> None:
        self._readiness_errors[identity.resource_name()] = error
