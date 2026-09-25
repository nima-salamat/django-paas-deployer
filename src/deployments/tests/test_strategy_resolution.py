from __future__ import annotations

from types import SimpleNamespace

import pytest

from deployments.application import (
    DeploymentRequest,
    DeploymentStrategyKind,
    DeploymentStrategyResolver,
    StrategyResolutionError,
)


def _strategy(label):
    return SimpleNamespace(label=label)


def test_database_platforms_use_database_strategy_without_reimplementing_lifecycle():
    app = _strategy("application")
    db = _strategy("database")
    resolver = DeploymentStrategyResolver(
        application_factory=lambda request: app,
        database_factory=lambda request: db,
        database_platforms={"postgresql", "redis"},
    )

    resolved = resolver.resolve(
        DeploymentRequest(
            platform="PostgreSQL",
            service_id="service-1",
            deployment_id="deploy-1",
        )
    )

    assert resolved.kind is DeploymentStrategyKind.DATABASE
    assert resolved.strategy is db
    assert resolved.platform == "postgresql"


def test_application_platforms_use_application_strategy():
    app = _strategy("application")
    resolver = DeploymentStrategyResolver(
        application_factory=lambda request: app,
        database_factory=None,
        database_platforms={"postgresql"},
    )

    resolved = resolver.resolve(
        DeploymentRequest(
            platform="Django",
            service_id="service-1",
            deployment_id="deploy-1",
        )
    )

    assert resolved.kind is DeploymentStrategyKind.APPLICATION
    assert resolved.strategy is app


def test_explicit_application_strategy_cannot_route_a_database_platform():
    resolver = DeploymentStrategyResolver(
        application_factory=lambda request: _strategy("application"),
        database_factory=lambda request: _strategy("database"),
        database_platforms={"postgresql"},
    )

    with pytest.raises(StrategyResolutionError, match="cannot use the application") as exc:
        resolver.resolve(
            DeploymentRequest(
                platform="postgresql",
                service_id="service-1",
                deployment_id="deploy-1",
                requested_kind=DeploymentStrategyKind.APPLICATION,
            )
        )
    assert exc.value.code == "strategy_kind_mismatch"


def test_missing_specialized_factory_is_a_controlled_resolution_error():
    resolver = DeploymentStrategyResolver(
        application_factory=lambda request: _strategy("application"),
        database_factory=None,
        database_platforms={"postgresql"},
    )

    with pytest.raises(StrategyResolutionError, match="No database deployment strategy"):
        resolver.resolve(
            DeploymentRequest(
                platform="postgresql",
                service_id="service-1",
                deployment_id="deploy-1",
            )
        )
