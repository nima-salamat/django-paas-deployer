from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from deployments.core.runtime_graph import ServiceRuntimeGraph
from deployments.core.swarm import SwarmRuntime, compile_compose_service
from deployments.core.types import DeploymentConfig
from deployments.runtime.execution_contract import (
    RuntimeExecutionContract,
    validate_swarm_contract,
    worker_provenance,
)


def _config(**overrides):
    base = DeploymentConfig(
        name="demo",
        tag="r1",
        zip_path="/tmp/demo.zip",
        dockerfile_template="FROM alpine:3.20",
        max_cpu=1.0,
        max_ram=512,
        networks=[],
        volumes=[],
        port=None,
        read_only=False,
        platform="docker",
        platform_type="app",
        start_command="python app.py",
        environment={},
        runtime_options={},
        labels={
            "service.id": "service-1",
            "deployment.id": "deployment-1",
            "revision.id": "revision-1",
            "release.id": "release-1",
            "process.name": "web",
        },
    )
    return replace(base, **overrides)


def test_wordpress_image_owned_contract_maps_cmd_to_swarm_args():
    contract = RuntimeExecutionContract.from_runtime(
        process_name="web",
        process_command="/usr/local/bin/passdeployer-wordpress-entrypoint.sh apache2-foreground",
        process_entrypoint="/bin/sh -lc",
        runtime_options={"catalog_managed": True},
        dockerfile=(
            "FROM wordpress:7.1.2-php8.4-apache\n"
            'ENTRYPOINT ["docker-ensure-installed.sh"]\n'
            'CMD ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh", "apache2-foreground"]\n'
        ),
        source_kind="catalog",
    )

    assert contract.entrypoint_source == "IMAGE"
    assert contract.image_entrypoint == ("docker-ensure-installed.sh",)
    assert contract.command is None
    assert contract.args == (
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
        "apache2-foreground",
    )

    spec = compile_compose_service(
        _config(
            dockerfile_template=(
                "FROM wordpress:7.1.2-php8.4-apache\n"
                'ENTRYPOINT ["docker-ensure-installed.sh"]\n'
                'CMD ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh", "apache2-foreground"]\n'
            ),
            entry_point="/bin/sh -lc",
            start_command="/usr/local/bin/passdeployer-wordpress-entrypoint.sh apache2-foreground",
            runtime_options={"catalog_managed": True},
        ),
        image_ref="wordpress:r1",
    )
    service = spec["services"]["demo"]
    assert service["command"] is None
    assert service["args"] == [
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
        "apache2-foreground",
    ]


def test_user_entrypoint_preserves_command_as_swarm_args():
    contract = RuntimeExecutionContract.from_runtime(
        process_name="web",
        process_entrypoint="/entrypoint.sh",
        process_command="gunicorn app:app --bind 0.0.0.0:8000",
    )
    assert contract.entrypoint_source == "USER"
    assert contract.command == ("/bin/sh", "-lc", "/entrypoint.sh")
    assert contract.args == ("gunicorn", "app:app", "--bind", "0.0.0.0:8000")

    spec = compile_compose_service(
        _config(
            entry_point="/entrypoint.sh",
            start_command="gunicorn app:app --bind 0.0.0.0:8000",
        ),
        image_ref="demo:r1",
    )
    service = spec["services"]["demo"]
    assert service["command"] == ["/bin/sh", "-lc", "/entrypoint.sh"]
    assert service["args"] == [
        "gunicorn",
        "app:app",
        "--bind",
        "0.0.0.0:8000",
    ]


def test_exact_production_bad_swarm_state_is_rejected_before_service_mutation(monkeypatch):
    config = _config(
        dockerfile_template=(
            "FROM wordpress:7.1.2-php8.4-apache\n"
            'ENTRYPOINT ["docker-ensure-installed.sh"]\n'
            'CMD ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh", "apache2-foreground"]\n'
        ),
        entry_point=None,
        start_command="/usr/local/bin/passdeployer-wordpress-entrypoint.sh apache2-foreground",
        runtime_options={"catalog_managed": True},
    )
    spec = compile_compose_service(config, image_ref="wordpress:r1")
    service = spec["services"]["demo"]

    # Reproduce the production container contract exactly: the shell wrapper
    # was materialized as both the command and effective entrypoint.
    service["entrypoint"] = ["/bin/sh", "-lc", "/usr/local/bin/passdeployer-wordpress-entrypoint.sh apache2-foreground"]
    service["command"] = ["/bin/sh", "-lc", "/usr/local/bin/passdeployer-wordpress-entrypoint.sh apache2-foreground"]
    service["args"] = []

    runtime = SwarmRuntime.__new__(SwarmRuntime)
    runtime._last_apply_operation = None
    runtime._last_apply_recovery = {}

    with patch.object(runtime, "_apply_local_volume_pin", return_value=[]):
        with pytest.raises(Exception) as exc:
            runtime._create_kwargs(config, image_ref="wordpress:r1", compose_spec=spec)

    error = exc.value
    assert error.code == "RUNTIME_ENTRYPOINT_CONTRACT_VIOLATION"
    assert error.details["boundary"] == "swarm_container_spec"
    assert error.details["expected_command"] is None
    assert error.details["expected_args"] == [
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
        "apache2-foreground",
    ]
    assert error.details["actual_command"] == service["command"]
    assert error.details["actual_args"] == []
    assert error.details["deployment_id"] == "deployment-1"
    assert error.details["service_id"] == "service-1"
    assert error.details["revision_id"] == "revision-1"
    assert "worker_code_revision" not in error.details or error.details["worker_code_revision"]


def test_observed_bad_swarm_contract_is_classified_as_runtime_contract_violation():
    runtime = SwarmRuntime.__new__(SwarmRuntime)
    service = MagicMock()
    service.attrs = {
        "Spec": {
            "TaskTemplate": {
                "ContainerSpec": {
                    "Command": ["/bin/sh", "-lc", "/usr/local/bin/passdeployer-wordpress-entrypoint.sh apache2-foreground"],
                    "Args": [],
                }
            }
        }
    }
    runtime.client = MagicMock()
    runtime.client.services.get.return_value = service

    contract = RuntimeExecutionContract(
        entrypoint_source="IMAGE",
        image_entrypoint=("docker-ensure-installed.sh",),
        image_cmd=(
            "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
            "apache2-foreground",
        ),
        command=None,
        args=(
            "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
            "apache2-foreground",
        ),
        catalog_managed=True,
        image_entrypoint_owned=True,
        process_name="web",
        source_kind="catalog",
    )

    error = runtime._runtime_contract_failure(
        "wordpress-service",
        contract=contract,
        expected_image="wordpress:r1",
        provenance={"deployment_id": "deployment-1", "service_id": "service-1"},
    )
    assert error is not None
    assert error.code == "RUNTIME_ENTRYPOINT_CONTRACT_VIOLATION"
    assert error.details["first_detected_boundary"] == "swarm_container_spec"
    assert error.details["expected"]["Command"] is None
    assert error.details["actual"]["command"] == [
        "/bin/sh", "-lc",
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh apache2-foreground",
    ]


def test_runtime_contract_fingerprint_is_deterministic_and_boundary_specific():
    contract = RuntimeExecutionContract(
        entrypoint_source="IMAGE",
        image_entrypoint=("docker-ensure-installed.sh",),
        image_cmd=("app", "serve"),
        args=("app", "serve"),
        image_entrypoint_owned=True,
    )
    assert contract.fingerprint(boundary="revision") == contract.fingerprint(boundary="revision")
    assert contract.fingerprint(boundary="revision") != contract.fingerprint(boundary="plan")
    assert contract.fingerprint(boundary="revision", image_ref="a:r1") != contract.fingerprint(
        boundary="revision", image_ref="a:r2"
    )


def test_worker_provenance_uses_build_sha_and_safe_process_identity(monkeypatch):
    monkeypatch.setenv("PASSDEPLOYER_GIT_SHA", "abc123")
    provenance = worker_provenance()
    assert provenance["worker_code_revision"] == "abc123"
    assert provenance["worker_started_at"]
    assert ":" in provenance["worker_instance_id"]


def test_legacy_catalog_revision_recovers_image_owned_cmd_and_discards_stale_entrypoint():
    revision = SimpleNamespace(
        pk="revision-wordpress-legacy",
        revision_number=7,
        config_snapshot={"source_kind": "catalog", "catalog_managed": True},
        build_snapshot={
            "dockerfile": (
                "FROM wordpress:7.1.2-php8.4-apache\n"
                'ENTRYPOINT ["docker-ensure-installed.sh"]\n'
                'CMD ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh", "apache2-foreground"]\n'
            )
        },
        runtime_snapshot={"start_command": None, "entry_point": "/bin/sh -lc"},
        source_snapshot={
            "catalog_id": "wordpress",
            "variant_id": "wordpress-mariadb",
            "definition_version": "3",
        },
        process_snapshot=[{
            "name": "web",
            "process_type": "application",
            "command": "stale-command",
            "entrypoint": "/bin/sh -lc",
            "replicas": 1,
            "enabled": True,
        }],
        environment_snapshot={},
        endpoint_snapshot=[],
        volume_snapshot=[],
        network_snapshot=[],
        graph_snapshot={},
    )
    graph = ServiceRuntimeGraph.from_revision(revision)
    contract = graph.execution_contract

    assert contract is not None
    assert contract.entrypoint_source == "IMAGE"
    assert contract.image_entrypoint == ("docker-ensure-installed.sh",)
    assert contract.command is None
    assert contract.args == (
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
        "apache2-foreground",
    )
    assert graph.processes[0].entrypoint is None
    assert graph.metadata["catalog_id"] == "wordpress"
    assert graph.metadata["variant_id"] == "wordpress-mariadb"
    assert graph.metadata["definition_version"] == "3"
