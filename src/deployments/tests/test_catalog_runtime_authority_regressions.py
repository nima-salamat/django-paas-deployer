from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from deployments.common.exceptions import DeploymentError
from deployments.core.runtime_graph import ServiceRuntimeGraph
from deployments.core.swarm import SwarmRuntime
from deployments.runtime.execution_contract import RuntimeExecutionContract
from deployments.runtime.identity import RuntimeIdentity
from deployments.runtime.swarm.adapter import SwarmRuntimeAdapter
from services.revisioning import _catalog_revision_requires_refresh


WORDPRESS_DOCKERFILE = """FROM wordpress:7.1.2-php8.4-apache
ENTRYPOINT ["/usr/local/bin/docker-ensure-installed.sh"]
CMD ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh", "/usr/local/bin/apache2-foreground"]
"""


def test_catalog_image_cmd_replaces_stale_shell_wrapped_process_command():
    stale_command = (
        "/bin/sh -lc /usr/local/bin/passdeployer-wordpress-entrypoint.sh "
        "apache2-foreground"
    )
    revision = SimpleNamespace(
        pk="revision-wordpress-stale-command",
        revision_number=12,
        # Legacy revisions can lose their catalog source marker while the
        # immutable runtime snapshot still records that this is a managed app.
        config_snapshot={"source_kind": "docker"},
        source_snapshot={"definition_version": "1.3"},
        build_snapshot={
            "dockerfile": WORDPRESS_DOCKERFILE,
            "files": {
                "passdeployer-wordpress-entrypoint.sh": "#!/bin/sh\nset -eu\n"
            },
        },
        runtime_snapshot={
            "catalog_managed": True,
            "start_command": stale_command,
            "entry_point": "/bin/sh -lc",
            # Old runtime snapshots may carry a serialized contract that bypasses
            # Dockerfile inspection and incorrectly treats the shell wrapper as
            # the process executable.
            "execution_contract": {
                "entrypoint_source": "PLATFORM",
                "image_entrypoint": [],
                "image_cmd": [],
                "command": ["/bin/sh", "-lc", stale_command],
                "args": [],
                "catalog_managed": False,
                "image_entrypoint_owned": False,
                "process_name": "web",
                "contract_version": "1",
                "required_executables": [],
                "source_kind": "docker",
            },
            "execution_contracts": {
                "web": {
                    "entrypoint_source": "PLATFORM",
                    "image_entrypoint": [],
                    "image_cmd": [],
                    "command": ["/bin/sh", "-lc", stale_command],
                    "args": [],
                    "catalog_managed": False,
                    "image_entrypoint_owned": False,
                    "process_name": "web",
                    "contract_version": "1",
                    "required_executables": [],
                    "source_kind": "docker",
                }
            },
            "execution_contract_hashes": {"revision_contract_hash": "old-contract"},
        },
        process_snapshot=[{
            "name": "web",
            "process_type": "web",
            "command": stale_command,
            "entrypoint": "/bin/sh -lc",
            "execution_contract": {
                "entrypoint_source": "PLATFORM",
                "image_entrypoint": [],
                "image_cmd": [],
                "command": ["/bin/sh", "-lc", stale_command],
                "args": [],
                "catalog_managed": False,
                "image_entrypoint_owned": False,
                "process_name": "web",
                "contract_version": "1",
                "required_executables": [],
                "source_kind": "docker",
            },
            "replicas": 1,
            "enabled": True,
        }],
        environment_snapshot={},
        endpoint_snapshot=[],
        volume_snapshot=[],
        network_snapshot=[],
    )

    graph = ServiceRuntimeGraph.from_revision(revision)

    assert graph.processes[0].command == (
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh "
        "/usr/local/bin/apache2-foreground"
    )
    assert graph.processes[0].entrypoint is None
    assert graph.execution_contract is not None
    assert graph.execution_contract.entrypoint_source == "IMAGE"
    assert graph.execution_contract.image_entrypoint == (
        "/usr/local/bin/docker-ensure-installed.sh",
    )
    assert graph.execution_contract.image_cmd == (
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
        "/usr/local/bin/apache2-foreground",
    )
    assert graph.execution_contract.command is None
    assert graph.execution_contract.args == (
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
        "/usr/local/bin/apache2-foreground",
    )


def test_catalog_revision_refresh_checks_dockerfile_even_if_current_files_are_empty():
    service = SimpleNamespace(
        source_kind="catalog",
        build_config={
            "dockerfile": WORDPRESS_DOCKERFILE,
            "files": {},
        },
    )
    revision = SimpleNamespace(
        config_snapshot={"source_kind": "catalog"},
        build_snapshot={
            "dockerfile": (
                "FROM wordpress:7.1.2-php8.4-apache\n"
                'ENTRYPOINT ["docker-entrypoint.sh"]\n'
                'CMD ["apache2-foreground"]\n'
            ),
            "files": {},
        },
    )

    assert _catalog_revision_requires_refresh(service, revision) is True



def test_catalog_image_preflight_rejects_stale_image_cmd():
    client = MagicMock()
    image = MagicMock()
    image.attrs = {
        "Id": "sha256:wordpress-artifact",
        "RepoDigests": ["registry.example/wordpress@sha256:wordpress-artifact"],
        "Config": {
            "Entrypoint": ["/usr/local/bin/docker-ensure-installed.sh"],
            "Cmd": [
                "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
                "apache2-foreground",
            ],
        },
        "Os": "linux",
        "Architecture": "amd64",
    }
    client.images.get.return_value = image
    runtime = SwarmRuntime(client)
    contract = RuntimeExecutionContract(
        entrypoint_source="IMAGE",
        image_entrypoint=("/usr/local/bin/docker-ensure-installed.sh",),
        image_cmd=(
            "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
            "/usr/local/bin/apache2-foreground",
        ),
        command=None,
        args=(
            "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
            "/usr/local/bin/apache2-foreground",
        ),
        catalog_managed=True,
        image_entrypoint_owned=True,
    )

    with pytest.raises(DeploymentError) as exc:
        runtime._validate_image_artifact("wordpress:stale", contract=contract)

    assert exc.value.code == "RUNTIME_ARTIFACT_CMD_MISMATCH"
    assert exc.value.details["expected_cmd"] == [
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
        "/usr/local/bin/apache2-foreground",
    ]
    assert exc.value.details["image_cmd"] == [
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
        "apache2-foreground",
    ]



def test_swarm_adapter_does_not_forward_stale_runtime_options_processes():
    stale_command = (
        "/bin/sh -lc /usr/local/bin/passdeployer-wordpress-entrypoint.sh "
        "apache2-foreground"
    )
    revision = SimpleNamespace(
        pk="revision-wordpress-stale-options",
        revision_number=13,
        config_snapshot={"source_kind": "catalog", "catalog_managed": True},
        source_snapshot={"catalog_id": "wordpress", "definition_version": "1.3"},
        build_snapshot={
            "dockerfile": WORDPRESS_DOCKERFILE,
            "files": {
                "passdeployer-wordpress-entrypoint.sh": "#!/bin/sh\\nset -eu\\n"
            },
        },
        runtime_snapshot={
            "catalog_managed": True,
            "start_command": stale_command,
        },
        process_snapshot=[{
            "name": "web",
            "process_type": "web",
            "command": stale_command,
            "entrypoint": "/bin/sh -lc",
            "replicas": 1,
            "enabled": True,
        }],
        environment_snapshot={},
        endpoint_snapshot=[],
        volume_snapshot=[],
        network_snapshot=[],
    )
    graph = ServiceRuntimeGraph.from_revision(revision)
    plan = SimpleNamespace(
        identity=RuntimeIdentity(
            service_id="service-wordpress",
            deployment_id="deploy-wordpress",
            revision_id="revision-wordpress-stale-options",
            runtime_name="app-wordpress",
        ),
        process_graph=graph,
        execution_contracts=graph.execution_contracts,
        image_ref="wordpress:test",
        artifact_digest="",
        release_id="release-wordpress",
        environment={},
        labels={},
        runtime_options={
            "catalog_managed": True,
            "image_entrypoint_owned": True,
            "processes": [{
                "name": "web",
                "process_type": "web",
                "command": stale_command,
                "entrypoint": "/bin/sh -lc",
                "enabled": True,
                "replicas": 1,
            }],
        },
        networks=(),
        volumes=(),
        endpoints=(),
        resources={},
        health_policy={},
    )

    spec, _ = SwarmRuntimeAdapter._plan_config(plan)

    assert spec.runtime_options["processes"][0]["command"] == (
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh "
        "/usr/local/bin/apache2-foreground"
    )
    assert spec.runtime_options["processes"][0]["entrypoint"] is None
    assert spec.runtime_options["processes"][0]["execution_contract"]["entrypoint_source"] == "IMAGE"
