"""Runtime-neutral observations returned by adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from .identity import RuntimeIdentity


class RuntimeObservedStatus(str, Enum):
    MISSING = "missing"
    PROVISIONING = "provisioning"
    READY = "ready"
    STOPPED = "stopped"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RuntimeTaskObservation:
    task_id: str
    desired_state: str = ""
    state: str = ""
    node_id: str | None = None
    node_name: str | None = None
    error: str = ""
    message: str = ""


@dataclass(frozen=True)
class RuntimeObservation:
    identity: RuntimeIdentity
    status: RuntimeObservedStatus
    runtime_id: str | None = None
    desired_replicas: int = 0
    ready_replicas: int = 0
    revision_id: str | None = None
    tasks: tuple[RuntimeTaskObservation, ...] = ()
    observed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def exists(self) -> bool:
        return self.status != RuntimeObservedStatus.MISSING

    @property
    def ready(self) -> bool:
        return self.status == RuntimeObservedStatus.READY
