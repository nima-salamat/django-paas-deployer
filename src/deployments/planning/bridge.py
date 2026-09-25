"""Temporary bridge from DeploymentPlan to the legacy executor DTO."""

from __future__ import annotations

from dataclasses import replace

from deployments.core.types import DeploymentConfig

from .plan import DeploymentPlan


class DeploymentPlanCompatibilityCompiler:
    """Keep the current orchestrator behavior while planning is migrated."""

    transitional = True

    def compile(
        self,
        plan: DeploymentPlan,
        *,
        base_config: DeploymentConfig | None = None,
    ) -> DeploymentConfig:
        config = base_config or plan.deployment_config
        if not isinstance(config, DeploymentConfig):
            raise TypeError(
                "The transitional plan bridge requires the existing DeploymentConfig."
            )

        runtime_options = dict(config.runtime_options or {})
        if plan.placement:
            runtime_options["placement_constraints"] = list(plan.placement)
        # DeploymentPlan.health_policy includes application readiness fields
        # such as path/expected_status.  Only translate Docker healthcheck
        # fields here; never overwrite an existing Docker healthcheck with a
        # readiness-policy dictionary.
        docker_healthcheck_keys = {
            "test", "cmd", "command", "interval", "timeout",
            "start_period", "start-period", "retries", "disable",
        }
        has_docker_healthcheck = any(
            key in plan.health_policy
            for key in {"test", "cmd", "command", "disable"}
        )
        docker_healthcheck = {
            key: value
            for key, value in plan.health_policy.items()
            if key in docker_healthcheck_keys
        }
        if has_docker_healthcheck and docker_healthcheck:
            runtime_options["healthcheck"] = docker_healthcheck

        labels = dict(config.labels or {})
        labels["service.id"] = str(plan.identity.service_id)
        if plan.identity.deployment_id:
            labels["deployment.id"] = str(plan.identity.deployment_id)
        if plan.identity.revision_id:
            labels["revision.id"] = str(plan.identity.revision_id)
        labels["passdeployer.strategy"] = str(plan.strategy_kind)

        return replace(
            config,
            environment=dict(plan.environment),
            networks=list(plan.networks),
            volumes=list(plan.volumes),
            endpoints=list(plan.endpoints),
            resource_limits=dict(plan.resources),
            runtime_options=runtime_options,
            labels=labels,
        )
