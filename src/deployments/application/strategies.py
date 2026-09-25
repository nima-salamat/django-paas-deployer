"""Strategy selection and specialized lifecycle hooks.

Application and database deployments share the lifecycle executor, runtime
contract, ownership fence, and event shape. They do not share their planning
or activation details. This module is deliberately small: it defines the
selection boundary without importing Django models, Celery, or Docker.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable

from deployments.runtime.contract import RuntimeOperationResult

from .context import DeploymentExecutionContext
from .lifecycle import DeploymentStrategy


class DeploymentStrategyKind(str, Enum):
    APPLICATION = "application"
    DATABASE = "database"
    SPECIALIZED = "specialized"


class StrategyResolutionError(ValueError):
    """The requested workload cannot be routed to a deployment strategy."""

    def __init__(self, message: str, *, code: str = "strategy_unavailable") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DeploymentRequest:
    """Minimal strategy-selection input at the application boundary."""

    platform: str
    service_id: str
    deployment_id: str
    requested_kind: DeploymentStrategyKind | None = None

    @property
    def normalized_platform(self) -> str:
        return str(self.platform or "").strip().lower()


@dataclass(frozen=True)
class ResolvedDeploymentStrategy:
    kind: DeploymentStrategyKind
    strategy: DeploymentStrategy
    platform: str


PlanBuilder = Callable[[DeploymentExecutionContext], Any]
ActivationHook = Callable[
    [DeploymentExecutionContext, Any, RuntimeOperationResult], None
]
StrategyFactory = Callable[[DeploymentRequest], DeploymentStrategy]


class CallbackDeploymentStrategy:
    """Adapt a specialized planner and activation hook to the shared port."""

    def __init__(
        self,
        *,
        build_plan: PlanBuilder,
        activate_plan: ActivationHook | None = None,
    ) -> None:
        self._build_plan = build_plan
        self._activate_plan = activate_plan

    def plan(self, context: DeploymentExecutionContext) -> Any:
        return self._build_plan(context)

    def activate(
        self,
        context: DeploymentExecutionContext,
        plan: Any,
        readiness: RuntimeOperationResult,
    ) -> None:
        if self._activate_plan is not None:
            self._activate_plan(context, plan, readiness)


class ApplicationDeploymentStrategy(CallbackDeploymentStrategy):
    kind = DeploymentStrategyKind.APPLICATION


class DatabaseDeploymentStrategy(CallbackDeploymentStrategy):
    kind = DeploymentStrategyKind.DATABASE


class DeploymentStrategyResolver:
    """Resolve exactly one specialized strategy at the composition boundary."""

    def __init__(
        self,
        *,
        application_factory: StrategyFactory | None,
        database_factory: StrategyFactory | None,
        database_platforms: Iterable[str],
    ) -> None:
        self._application_factory = application_factory
        self._database_factory = database_factory
        self._database_platforms = frozenset(
            str(value).strip().lower() for value in database_platforms
        )

    def resolve(self, request: DeploymentRequest) -> ResolvedDeploymentStrategy:
        platform = request.normalized_platform
        inferred = (
            DeploymentStrategyKind.DATABASE
            if platform in self._database_platforms
            else DeploymentStrategyKind.APPLICATION
        )
        kind = request.requested_kind or inferred

        if kind is DeploymentStrategyKind.DATABASE and platform not in self._database_platforms:
            raise StrategyResolutionError(
                f"Platform '{platform}' is not a database workload.",
                code="strategy_kind_mismatch",
            )
        if kind is DeploymentStrategyKind.APPLICATION and platform in self._database_platforms:
            raise StrategyResolutionError(
                f"Database platform '{platform}' cannot use the application strategy.",
                code="strategy_kind_mismatch",
            )
        if kind is DeploymentStrategyKind.SPECIALIZED:
            raise StrategyResolutionError(
                "Specialized strategies must be registered explicitly.",
                code="strategy_not_registered",
            )

        factory = (
            self._database_factory
            if kind is DeploymentStrategyKind.DATABASE
            else self._application_factory
        )
        if factory is None:
            raise StrategyResolutionError(
                f"No {kind.value} deployment strategy is registered.",
                code="strategy_not_registered",
            )
        strategy = factory(request)
        if strategy is None:
            raise StrategyResolutionError(
                f"The {kind.value} deployment strategy factory returned no strategy.",
                code="strategy_not_registered",
            )
        return ResolvedDeploymentStrategy(
            kind=kind,
            strategy=strategy,
            platform=platform,
        )
