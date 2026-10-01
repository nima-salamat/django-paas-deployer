"""Central deployment wall-clock deadline abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class DeploymentDeadline:
    deadline: datetime | None
    phase: str = "application"

    def remaining(self, *, now: datetime | None = None) -> float | None:
        if self.deadline is None:
            return None
        current = now or datetime.now(self.deadline.tzinfo)
        return max(0.0, (self.deadline - current).total_seconds())

    def bound(self, configured: float | int | None, *, now: datetime | None = None) -> float | None:
        remaining = self.remaining(now=now)
        if remaining is None:
            return None if configured is None else max(0.0, float(configured))
        return remaining if configured is None else max(0.0, min(float(configured), remaining))

    def expired(self, *, now: datetime | None = None) -> bool:
        value = self.remaining(now=now)
        return value is not None and value <= 0

__all__ = ["DeploymentDeadline"]
