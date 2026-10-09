"""Trace the catalog's executable path into the compiled Swarm contract.

This is the source-to-spec half of the end-to-end Docker/Swarm workflow. The
workflow additionally probes the actual built image and launched container.
"""
from pathlib import Path
import shlex

import yaml

from deployments.core.swarm import compile_compose_service
from deployments.core.types import DeploymentConfig
from deployments.runtime.execution_contract import RuntimeExecutionContract
from deployments.celery.services.deploy_service import _merge_revision_runtime_environment


def test_wordpress_catalog_executable_paths_reach_swarm_unchanged():
    repo_src = Path(__file__).resolve().parents[2]
    catalog_path = (
        repo_src
        / "app_catalog"
        / "catalog"
        / "first_party"
        / "wordpress-with-mariadb.yaml"
    )
    document = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    spec = document["services"]["wordpress"]
    dockerfile = str(spec["dockerfile"])
    dockerfile = dockerfile.replace("${config.software_version}", "7.1.2")
    dockerfile = dockerfile.replace("${config.php_version}", "8.4")
    command = [str(value) for value in spec["command"]]

    # Trace the definition's exact exec-form ENTRYPOINT/CMD through the
    # contract builder and into the Compose-shaped spec consumed by Swarm.
    contract = RuntimeExecutionContract.from_runtime(
        process_name="web",
        process_command=shlex.join(command),
        process_entrypoint=None,
        runtime_options={
            "catalog_managed": True,
            "image_entrypoint_owned": True,
            "source_kind": "catalog",
        },
        source_kind="catalog",
        dockerfile=dockerfile,
    )
    assert contract.entrypoint_source == "IMAGE"
    assert contract.image_entrypoint == (
        "/usr/local/bin/docker-ensure-installed.sh",
    )
    assert contract.args == tuple(command)
    assert contract.required_executables == (
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
    )

    config = DeploymentConfig(
        name="wordpress-path-trace",
        tag="r1",
        zip_path="/tmp/wordpress-path-trace.zip",
        dockerfile_template=dockerfile,
        max_cpu=1.0,
        max_ram=512,
        networks=[],
        volumes=[],
        port=80,
        read_only=False,
        platform="docker",
        platform_type="app",
        start_command=shlex.join(command),
        entry_point=None,
        environment={
            "PATH": str(spec["environment"]["PATH"]),
        },
        runtime_options={
            "catalog_managed": True,
            "image_entrypoint_owned": True,
            "source_kind": "catalog",
        },
        working_directory=str(spec["working_dir"]),
    )
    compiled = compile_compose_service(config, image_ref="wordpress:path-trace")
    service = compiled["services"]["wordpress-path-trace"]

    assert service["command"] is None
    assert service["args"] == command
    assert service["entrypoint"] is None

    # The downstream executable must be checked in the actual image at build
    # time, not merely accepted as a string in Swarm Args.
    assert "test -x /usr/local/bin/apache2-foreground" in dockerfile
    assert service["environment"] == [
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    ]



def test_materialized_runtime_secrets_survive_non_secret_runtime_graph():
    graph_environment = {
        "WORDPRESS_DB_HOST": "mariadb",
        "WORDPRESS_DB_NAME": "wordpress",
        "WORDPRESS_SITE_TITLE": "Example",
    }
    materialized_environment = {
        **graph_environment,
        "WORDPRESS_DB_PASSWORD": "db-secret-version-4",
        "WORDPRESS_ADMIN_PASSWORD": "admin-secret-version-2",
        "BUILD_ONLY_SECRET": "must-not-enter-runtime",
        "UNREFERENCED_SECRET": "must-not-enter-runtime",
    }
    secret_refs = [
        {"path": "env.WORDPRESS_DB_PASSWORD", "scope": "runtime", "key": "service_password_wordpress", "version": 4},
        {"path": "env.WORDPRESS_ADMIN_PASSWORD", "scope": "both", "key": "wordpress_admin_password", "version": 2},
        {"path": "env.BUILD_ONLY_SECRET", "scope": "build", "key": "build_only_secret", "version": 1},
        {"path": "config.password", "scope": "runtime", "key": "password", "version": 1},
    ]

    result = _merge_revision_runtime_environment(
        graph_environment,
        materialized_environment,
        secret_refs,
    )

    assert result["WORDPRESS_DB_PASSWORD"] == "db-secret-version-4"
    assert result["WORDPRESS_ADMIN_PASSWORD"] == "admin-secret-version-2"
    assert result["WORDPRESS_DB_HOST"] == "mariadb"
    assert result["WORDPRESS_DB_NAME"] == "wordpress"
    assert result["WORDPRESS_SITE_TITLE"] == "Example"
    assert "BUILD_ONLY_SECRET" not in result
    assert "UNREFERENCED_SECRET" not in result
    assert "password" not in result
