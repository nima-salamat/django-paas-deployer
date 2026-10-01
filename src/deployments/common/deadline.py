"""Central deployment wall-clock deadline abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

@dataclass(frozen=True)
class DeploymentDeadline:
    """Absolute deadline shared by blocking deployment operations."""
    deadline: datetime | None
    phase: str = "application"

    @classmethod
    def from_deployment(cls, deployment, *, now: datetime | None = None):
        current = now or timezone.now()
        from core.settings_service import base_image_build_timeout_minutes, deploy_timeout_minutes
        phase = str(getattr(deployment, "stage", "") or "application").strip().lower()
        timeout_minutes = base_image_build_timeout_minutes() if phase == "base_image" else deploy_timeout_minutes()
        started = deployment.lifecycle_phase_started_at()
        deadline = None if started is None else started + timedelta(minutes=max(0, int(timeout_minutes)))
        return cls(deadline=deadline, phase=phase)

    def remaining(self, *, now: datetime | None = None) -> float | None:
        if self.deadline is None:
            return None
        current = now or timezone.now()
        return max(0.0, (self.deadline - current).total_seconds())

    def bound(self, configured: float | int | None, *, now: datetime | None = None) -> float | None:
        remaining = self.remaining(now=now)
        if remaining is None:
            return None if configured is None else max(0.0, float(configured))
        if configured is None:
            return remaining
        return max(0.0, min(float(configured), remaining))

    def expired(self, *, now: datetime | None = None) -> bool:
        value = self.remaining(now=now)
        return value is not None and value <= 0

__all__ = ["DeploymentDeadline"]
