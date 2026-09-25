"""Typed runtime capabilities and availability.

Capabilities describe what a backend can do.  Availability describes whether
it can do it now.  Keeping those concepts separate prevents an unavailable
Swarm manager from being confused with a backend that does not support a
requested operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class RuntimeCapability(str, Enum):
    SERVICE_SCHEDULING = "service_scheduling"
    REPLICAS = "replicas"
    ROLLING_UPDATE = "rolling_update"
    ROLLBACK = "rollback"
    NODE_CONSTRAINTS = "node_constraints"
    OVERLAY_NETWORKS = "overlay_networks"
    PERSISTENT_VOLUMES = "persistent_volumes"
    SERVICE_LOGS = "service_logs"
    HEALTH_CHECKS = "health_checks"
    PROCESS_GRAPH = "process_graph"


class RuntimeAvailabilityState(str, Enum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class RuntimeCapabilities:
    """Features supported by one runtime backend."""

    backend: str
    supported: frozenset[RuntimeCapability] = field(default_factory=frozenset)
    version: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def supports(self, *capabilities: RuntimeCapability) -> bool:
        return not self.missing(*capabilities)

    def missing(self, *capabilities: RuntimeCapability) -> frozenset[RuntimeCapability]:
        return frozenset(
            capability
            for capability in capabilities
            if capability not in self.supported
        )


@dataclass(frozen=True)
class RuntimeAvailability:
    """Current operational state of a runtime backend."""

    backend: str
    state: RuntimeAvailabilityState = RuntimeAvailabilityState.UNKNOWN
    operator_enabled: bool = True
    reachable: bool = False
    manager_capable: bool = False
    reason_code: str = ""
    message: str = ""
    checked_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def can_observe(self) -> bool:
        return self.operator_enabled and self.reachable

    @property
    def can_execute(self) -> bool:
        return (
            self.state == RuntimeAvailabilityState.ACTIVE
            and self.operator_enabled
            and self.reachable
            and self.manager_capable
        )


def coerce_capability(value: RuntimeCapability | str) -> RuntimeCapability:
    if isinstance(value, RuntimeCapability):
        return value
    return RuntimeCapability(str(value))


def capability_set(values: Any) -> frozenset[RuntimeCapability]:
    if not values:
        return frozenset()
    return frozenset(coerce_capability(value) for value in values)
