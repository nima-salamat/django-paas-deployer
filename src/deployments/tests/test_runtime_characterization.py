"""Characterization tests for behavior the runtime migration must preserve."""

from types import SimpleNamespace

import pytest

from deployments.core.runtime_graph import ServiceRuntimeGraph
from deployments.core.swarm import compile_compose_service
from deployments.core.types import DeploymentConfig, EndpointSpec, NetworkSpec, VolumeSpec


def _revision(**overrides):
    values = {
        "pk": "revision-1",
        "revision_number": 4,
        "source_snapshot": {"kind": "archive"},
        "build_snapshot": {"platform": "python"},
        "runtime_snapshot": {"read_only": False},
        "environment_snapshot": {
            "APP_ENV": {"value": "production", "scope": "runtime"},
        },
        "process_snapshot": [
            {
                "name": "web",
                "process_type": "web",
                "command": "gunicorn app.wsgi",
                "replicas": 1,
                "enabled": True,
                "environment": {"PROCESS_ENV": "1"},
                "healthcheck": {"path": "/healthz"},
                "resources": {"cpu": 1.0},
            }
        ],
        "endpoint_snapshot": [
            {
                "name": "http",
                "target_port": 8000,
                "exposure": "public",
                "protocol": "http",
                "hostname": "demo.example.test",
            }
        ],
        "volume_snapshot": [{"source": "demo-data", "target": "/data"}],
        "network_snapshot": ["demo-net"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _deployment_config(**overrides):
    values = {
        "name": "demo",
        "tag": "r4",
        "zip_path": "/tmp/demo.zip",
        "dockerfile_template": "FROM python:3.12",
        "max_cpu": 1.0,
        "max_ram": 512,
        "networks": [NetworkSpec(name="demo-net", driver="overlay")],
        "volumes": [VolumeSpec(source="demo-data", target="/data")],
        "port": 8000,
        "read_only": False,
        "platform": "python",
        "platform_type": "app",
        "start_command": "gunicorn app.wsgi",
        "environment": {"APP_ENV": "production"},
        "resource_limits": {"cpu": 1.0, "memory_mb": 512},
        "labels": {
            "service.id": "service-1",
            "deployment.id": "deployment-1",
            "process.name": "web",
        },
        "endpoints": [
            EndpointSpec(
                name="http",
                target_port=8000,
                published_port=8000,
                exposure="public",
                protocol="tcp",
                hostname="demo.example.test",
            )
        ],
    }
    values.update(overrides)
    return DeploymentConfig(**values)


def test_revision_graph_preserves_process_environment_and_runtime_resources():
    graph = ServiceRuntimeGraph.from_revision(_revision())

    assert graph.metadata == {"revision_id": "revision-1", "revision": 4}
    assert graph.runtime_environment == {"APP_ENV": "production"}
    assert graph.processes[0].environment == {"PROCESS_ENV": "1"}
    assert graph.networks == ("demo-net",)
    assert graph.volumes == ({"source": "demo-data", "target": "/data"},)
    assert graph.public_endpoints() == [
        {
            "name": "http",
            "target_port": 8000,
            "protocol": "http",
            "hostname": "demo.example.test",
            "path": "",
            "tls": False,
        }
    ]


def test_revision_graph_rejects_the_currently_unsupported_replica_shape():
    with pytest.raises(ValueError, match="exactly one replica"):
        ServiceRuntimeGraph.from_revision(
            _revision(
                process_snapshot=[
                    {"name": "worker", "process_type": "worker", "replicas": 2}
                ]
            )
        )


def test_swarm_compilation_preserves_current_runtime_identity_and_resources():
    spec = compile_compose_service(_deployment_config(), image_ref="demo:r4")
    service = spec["services"]["demo"]

    assert service["image"] == "demo:r4"
    assert service["environment"] == ["APP_ENV=production"]
    assert service["volumes"] == ["demo-data:/data:rw"]
    assert service["deploy"]["labels"]["passdeployer.service"] == "service-1"
    assert service["deploy"]["labels"]["passdeployer.deployment"] == "deployment-1"
    assert service["deploy"]["replicas"] == 1
    assert service["ports"] == [
        {"target": 8000, "published": 8000, "protocol": "tcp", "mode": "ingress"}
    ]


def test_deployment_config_image_identity_remains_name_and_tag():
    assert _deployment_config().image_ref == "demo:r4"
