"""Tests for configuration precedence, provenance, plans, and the bridge."""

from pathlib import Path
import pytest

from deployments.core.runtime_graph import RuntimeEndpoint, RuntimeProcess, ServiceRuntimeGraph
from deployments.runtime import RuntimeCapability, RuntimeIdentity, RuntimeRegistry
from deployments.runtime.fake import FakeRuntime
from deployments.planning import (
    ConfigurationResolutionError,
    ConfigurationResolver,
    DeploymentPlanCompatibilityCompiler,
    DeploymentPlanCompiler,
)
from deployments.tests.test_runtime_characterization import _deployment_config


def test_configuration_layers_have_explicit_precedence_and_explainability():
    resolver = ConfigurationResolver(
        defaults={"health_timeout": 60, "runtime_options": {"restart": "on-failure"}}
    )
    resolved = resolver.resolve(
        platform_policy={"health_timeout": 90, "max_replicas": 3},
        cluster_policy={"runtime_options": {"placement_constraints": ["node.role == worker"]}},
        service_intent={"replicas": 2, "runtime_options": {"restart": "unless-stopped"}},
        revision_snapshot={"environment": {"APP_ENV": "production"}},
        deployment_overrides={"healthcheck_timeout": 12},
    )

    assert resolved.get("health_timeout") == 90
    assert resolved.get("replicas") == 2
    assert resolved.get("runtime_options")["restart"] == "unless-stopped"
    assert resolved.get("runtime_options")["placement_constraints"] == [
        "node.role == worker"
    ]
    assert resolved.explain("healthcheck_timeout")["source"] == "deployment_request"
    assert resolved.explain("health_timeout")["source"] == "platform_policy"


def test_configuration_rejects_operator_policy_override_and_redacts_values():
    resolver = ConfigurationResolver()

    with pytest.raises(ConfigurationResolutionError) as exc:
        resolver.resolve(deployment_overrides={"resource_limits": {"cpu": 8}})
    assert exc.value.code == "deployment_override_forbidden"

    resolved = resolver.resolve(
        deployment_overrides={"environment": {"DB_PASSWORD": "do-not-show"}}
    )
    assert resolved.get("environment")["DB_PASSWORD"] == "do-not-show"
    assert resolved.explain("environment.DB_PASSWORD")["effective"] == "[REDACTED]"
    assert resolved.public_values()["environment"]["DB_PASSWORD"] == "[REDACTED]"


def test_configuration_rejects_replicas_above_platform_or_cluster_ceiling():
    with pytest.raises(ConfigurationResolutionError) as exc:
        ConfigurationResolver().resolve(
            platform_policy={"max_replicas": 4},
            cluster_policy={"max_replicas": 2},
            service_intent={"replicas": 3},
        )
    assert exc.value.code == "policy_rejects_replicas"
    assert exc.value.details == {"requested": 3, "effective_max": 2}


def _graph():
    return ServiceRuntimeGraph(
        runtime={"healthcheck": {"test": ["CMD", "true"]}},
        runtime_environment={"APP_ENV": "production"},
        processes=(
            RuntimeProcess(name="web", process_type="web", replicas=1),
        ),
        endpoints=(
            RuntimeEndpoint(
                name="http",
                target_port=8000,
                exposure="public",
                protocol="http",
                hostname="demo.example.test",
            ),
        ),
        volumes=({"source": "demo-data", "target": "/data"},),
        networks=("demo-net",),
    )


def test_plan_compiler_derives_capabilities_and_bridge_preserves_legacy_config():
    runtime = FakeRuntime()
    selection = RuntimeRegistry({"swarm": runtime}).resolve(policy={"backend": "swarm"})
    resolved = ConfigurationResolver().resolve(
        revision_snapshot={
            "runtime_options": {
                "placement_constraints": ["node.role == worker"],
            },
            "health_policy": {"timeout": 60},
        }
    )
    identity = RuntimeIdentity(
        service_id="service-1",
        deployment_id="deployment-1",
        revision_id="revision-1",
        runtime_name="app-service-1",
    )
    base = _deployment_config(
        runtime_options={"healthcheck": {"test": "true", "retries": 2}}
    )

    plan = DeploymentPlanCompiler().compile(
        identity=identity,
        graph=_graph(),
        selection=selection,
        resolved=resolved,
        image_ref="demo:r1",
        deployment_config=base,
    )
    bridged = DeploymentPlanCompatibilityCompiler().compile(plan)

    assert RuntimeCapability.SERVICE_SCHEDULING in plan.required_capabilities
    assert RuntimeCapability.PERSISTENT_VOLUMES in plan.required_capabilities
    assert RuntimeCapability.OVERLAY_NETWORKS in plan.required_capabilities
    assert RuntimeCapability.HEALTH_CHECKS in plan.required_capabilities
    assert plan.identity == identity
    assert bridged.image_ref == base.image_ref
    assert [network.name for network in bridged.networks] == ["demo-net"]
    assert [volume.target for volume in bridged.volumes] == ["/data"]
    assert bridged.labels["revision.id"] == "revision-1"
    assert bridged.runtime_options["placement_constraints"] == [
        "node.role == worker"
    ]
    assert bridged.runtime_options["healthcheck"] == {
        "test": "true",
        "retries": 2,
    }


def test_current_swarm_service_path_compiles_a_plan_before_the_legacy_facade():
    source = Path("src/deployments/celery/services/deploy_service.py").read_text()

    assert "def _compile_compatibility_plan(" in source
    assert "execution_plan = self._compile_compatibility_plan(" in source
    assert "execution_plan=execution_plan" in source
    assert "RuntimeRegistry.with_swarm().resolve(" in source
    assert "DeploymentPlanCompiler().compile(" in source
