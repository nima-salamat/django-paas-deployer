"""Deployment application-layer use-case primitives."""

from .context import DeploymentExecutionContext, DeploymentExecutionEvent
from .cancel import (
    CancelDeploymentUseCase,
    DeploymentCancellationGateway,
    DeploymentCancellationResult,
)
from .cancellation import (
    CancellationAction,
    DeploymentCancellationDecision,
    DeploymentCancellationSnapshot,
    decide_cancellation,
)
from .lifecycle import (
    DeploymentLifecycleExecutor,
    DeploymentLifecycleResult,
    InMemoryLifecycleStore,
)
from .strategies import (
    ApplicationDeploymentStrategy,
    DatabaseDeploymentStrategy,
    DeploymentRequest,
    DeploymentStrategyKind,
    DeploymentStrategyResolver,
    ResolvedDeploymentStrategy,
    StrategyResolutionError,
)

__all__ = [
    "DeploymentExecutionContext",
    "DeploymentExecutionEvent",
    "CancelDeploymentUseCase",
    "DeploymentCancellationGateway",
    "DeploymentCancellationResult",
    "CancellationAction",
    "DeploymentCancellationDecision",
    "DeploymentCancellationSnapshot",
    "decide_cancellation",
    "DeploymentLifecycleExecutor",
    "DeploymentLifecycleResult",
    "InMemoryLifecycleStore",
    "ApplicationDeploymentStrategy",
    "DatabaseDeploymentStrategy",
    "DeploymentRequest",
    "DeploymentStrategyKind",
    "DeploymentStrategyResolver",
    "ResolvedDeploymentStrategy",
    "StrategyResolutionError",
]
