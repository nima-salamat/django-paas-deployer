"""Stable runtime identity value object."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeIdentity:
    """Stable identity used to correlate a plan with observed resources."""

    service_id: str
    deployment_id: str | None = None
    revision_id: str | None = None
    process_name: str = "web"
    runtime_name: str = ""

    def resource_name(self) -> str:
        if self.runtime_name:
            return self.runtime_name
        return self.service_id
