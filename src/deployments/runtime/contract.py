"""The small runtime contract used by deployment application code."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, TYPE_CHECKING

from .capabilities import (
    RuntimeAvailability,
    RuntimeCapabilities,
    RuntimeCapability,
)
from .identity import RuntimeIdentity
from .observations import RuntimeObservation

if TYPE_CHECKING:  # pragma: no cover
    from .errors import RuntimeOperationError


class RuntimeBackend(str, Enum):
    SWARM = "swarm"
    LEGACY_DOCKER = "legacy_docker"


@dataclass(frozen=True)
class RuntimeHandle:
    backend: str
    identity: RuntimeIdentity
    runtime_id: str | None = None
    resource_name: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def with_metadata(self, **values: Any) -> "RuntimeHandle":
        metadata = dict(self.metadata)
        metadata.update(values)
        return replace(self, metadata=metadata)


@dataclass(frozen=True)
class RuntimeOperationResult:
    success: bool
    changed: bool = False
    idempotent: bool = False
    handle: RuntimeHandle | None = None
    observation: RuntimeObservation | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeSelection:
    """The result of resolving one deployment to one backend."""

    backend: str
    cluster: str | None
    required_capabilities: frozenset[RuntimeCapability]
    capabilities: RuntimeCapabilities
    availability: RuntimeAvailability
    reason: str

    @property
    def missing_capabilities(self) -> frozenset[RuntimeCapability]:
        return self.capabilities.missing(*self.required_capabilities)

    @property
    def can_execute(self) -> bool:
        return not self.missing_capabilities and self.availability.can_execute


class RuntimeContract(Protocol):
    """Operations required by the deployment application layer."""

    backend: str

    def describe_capabilities(self) -> RuntimeCapabilities:
        ...

    def check_availability(
        self, *, operator_enabled: bool | None = None
    ) -> RuntimeAvailability:
        ...

    def apply(self, plan: Any, *, operation_key: str) -> RuntimeOperationResult:
        ...

    def inspect(self, identity: RuntimeIdentity) -> RuntimeObservation:
        ...

    def wait_ready(
        self,
        handle: RuntimeHandle,
        *,
        timeout: float | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> RuntimeOperationResult:
        ...

    def stop(
        self, handle: RuntimeHandle, *, operation_key: str
    ) -> RuntimeOperationResult:
        ...

    def remove(
        self, handle: RuntimeHandle, *, operation_key: str
    ) -> RuntimeOperationResult:
        ...

    def rollback(
        self,
        plan: Any,
        *,
        operation_key: str,
        target_plan: Any | None = None,
    ) -> RuntimeOperationResult:
        ...

    def logs(self, identity: RuntimeIdentity, *, tail: int | str = 200) -> Any:
        ...
