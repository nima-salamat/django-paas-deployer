"""Application use case for requesting deployment cancellation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .cancellation import DeploymentCancellationDecision


@dataclass(frozen=True)
class DeploymentCancellationResult:
    """Outcome returned to presentation adapters after the locked update."""

    decision: DeploymentCancellationDecision
    execution_task_id: str = ""


class DeploymentCancellationGateway(Protocol):
    """Persistence boundary for the cancellation use case."""

    def cancel(self, deploy_id: int) -> DeploymentCancellationResult:
        ...


class CancelDeploymentUseCase:
    """Coordinate cancellation without exposing persistence details to APIs."""

    def __init__(self, gateway: DeploymentCancellationGateway) -> None:
        self.gateway = gateway

    def execute(self, deploy_id: int) -> DeploymentCancellationResult:
        return self.gateway.cancel(deploy_id)


__all__ = [
    "CancelDeploymentUseCase",
    "DeploymentCancellationGateway",
    "DeploymentCancellationResult",
]
