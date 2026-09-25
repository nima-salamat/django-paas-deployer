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
        if plan.health_policy:
            runtime_options["healthcheck"] = dict(plan.health_policy)

        labels = dict(config.labels or {})
        labels["service.id"] = str(plan.identity.service_id)
        if plan.identity.deployment_id:
            labels["deployment.id"] = str(plan.identity.deployment_id)
        if plan.identity.revision_id:
            labels["revision.id"] = str(plan.identity.revision_id)

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
