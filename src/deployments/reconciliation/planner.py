"""Pure reconciliation decisions.

The planner never calls Docker.  It compares service intent and revision
provenance with a runtime-neutral observation, then returns one idempotent
action for an adapter/executor to perform.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from deployments.runtime.capabilities import (
    RuntimeAvailabilityState,
    RuntimeCapability,
)
from deployments.runtime.contract import RuntimeSelection
from deployments.runtime.observations import RuntimeObservation, RuntimeObservedStatus


class ReconciliationAction(str, Enum):
    CONVERGED = "converged"
    CREATE = "create"
    UPDATE = "update"
    STOP = "stop"
    REPAIR = "repair"
    BLOCKED = "blocked"
    MANUAL_INTERVENTION = "manual_intervention"


@dataclass(frozen=True)
class DesiredRuntimeState:
    service_id: str
    revision_id: str | None
    desired_state: str
    runtime_name: str
    required_capabilities: frozenset[RuntimeCapability] = frozenset()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReconciliationDecision:
    action: ReconciliationAction
    reason_code: str
    message: str
    service_id: str
    runtime_name: str
    recoverable: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)


class ReconciliationPlanner:
    """Derive a safe, repeatable action from desired and observed state."""

    def decide(
        self,
        desired: DesiredRuntimeState,
        observed: RuntimeObservation,
        selection: RuntimeSelection,
    ) -> ReconciliationDecision:
        base = {
            "service_id": desired.service_id,
            "runtime_name": desired.runtime_name,
        }
        missing = selection.capabilities.missing(*desired.required_capabilities)
        if missing:
            return ReconciliationDecision(
                action=ReconciliationAction.BLOCKED,
                reason_code="runtime_capability_unsupported",
                message="The selected runtime cannot satisfy the desired service state.",
                recoverable=False,
                details={**base, "missing_capabilities": sorted(item.value for item in missing)},
                **base,
            )

        availability = selection.availability
        if not availability.can_execute:
            return ReconciliationDecision(
                action=ReconciliationAction.BLOCKED,
                reason_code=availability.reason_code or "runtime_unavailable",
                message=availability.message or "The selected runtime is not available for reconciliation.",
                recoverable=availability.state in {
                    RuntimeAvailabilityState.UNKNOWN,
                    RuntimeAvailabilityState.UNAVAILABLE,
                    RuntimeAvailabilityState.DEGRADED,
                },
                details={
                    **base,
                    "availability": availability.state.value,
                    "reachable": availability.reachable,
                    "manager_capable": availability.manager_capable,
                },
                **base,
            )

        desired_state = str(desired.desired_state or "").lower()
        if desired_state not in {"running", "stopped"}:
            return ReconciliationDecision(
                action=ReconciliationAction.MANUAL_INTERVENTION,
                reason_code="desired_state_unknown",
                message=f"Desired runtime state {desired.desired_state!r} is not supported.",
                details={**base, "desired_state": desired.desired_state},
                **base,
            )

        if desired_state == "stopped":
            if observed.status in {RuntimeObservedStatus.MISSING, RuntimeObservedStatus.STOPPED}:
                return self._converged(desired, "desired_stopped")
            return ReconciliationDecision(
                action=ReconciliationAction.STOP,
                reason_code="runtime_should_be_stopped",
                message="The runtime resource is running while the service is desired stopped.",
                recoverable=True,
                details={**base, "observed_status": observed.status.value},
                **base,
            )

        if observed.status == RuntimeObservedStatus.MISSING:
            return ReconciliationDecision(
                action=ReconciliationAction.CREATE,
                reason_code="runtime_resource_missing",
                message="The desired running resource is missing from the runtime.",
                recoverable=True,
                details={**base, "revision_id": desired.revision_id},
                **base,
            )

        if observed.status in {RuntimeObservedStatus.FAILED, RuntimeObservedStatus.DEGRADED}:
            return ReconciliationDecision(
                action=ReconciliationAction.REPAIR,
                reason_code="runtime_resource_unhealthy",
                message="The desired running resource is not healthy in the runtime.",
                recoverable=True,
                details={
                    **base,
                    "observed_status": observed.status.value,
                    "revision_id": desired.revision_id,
                },
                **base,
            )

        if desired.revision_id and observed.revision_id != desired.revision_id:
            if observed.revision_id:
                return ReconciliationDecision(
                    action=ReconciliationAction.UPDATE,
                    reason_code="runtime_revision_drift",
                    message="The observed runtime revision differs from the desired revision.",
                    recoverable=True,
                    details={
                        **base,
                        "desired_revision_id": desired.revision_id,
                        "observed_revision_id": observed.revision_id,
                    },
                    **base,
                )
            return ReconciliationDecision(
                action=ReconciliationAction.MANUAL_INTERVENTION,
                reason_code="runtime_revision_unknown",
                message="The runtime exists but its revision identity is unknown.",
                recoverable=False,
                details={**base, "desired_revision_id": desired.revision_id},
                **base,
            )

        if observed.status == RuntimeObservedStatus.READY:
            return self._converged(desired, "desired_running")

        return ReconciliationDecision(
            action=ReconciliationAction.REPAIR,
            reason_code="runtime_not_ready",
            message="The desired runtime resource exists but is not ready.",
            recoverable=True,
            details={**base, "observed_status": observed.status.value},
            **base,
        )

    @staticmethod
    def _converged(desired: DesiredRuntimeState, reason: str) -> ReconciliationDecision:
        return ReconciliationDecision(
            action=ReconciliationAction.CONVERGED,
            reason_code=reason,
            message="Desired and observed runtime state are converged.",
            service_id=desired.service_id,
            runtime_name=desired.runtime_name,
            details={"desired_state": desired.desired_state, "revision_id": desired.revision_id},
        )
