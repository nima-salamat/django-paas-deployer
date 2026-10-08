import io
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from deployments.core.platform_bridge import enrich_config_from_project
from deployments.core.types import DeploymentConfig


def _project_cfg(**overrides):
    values = {
        "platform": "docker",
        "framework": "wordpress",
        "start_command": "apache2-foreground",
        "server_type": None,
        "runtime_version": None,
        "package_manager": None,
        "working_directory": None,
        "build_dir": None,
        "output_dir": None,
        "static_dir": None,
        "build_command": None,
        "install_command": None,
        "extra": {},
        "port": 80,
        "environment": {},
        "sources": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _detection():
    return SimpleNamespace(
        platform="docker",
        framework="wordpress",
        confidence=1.0,
        matched_files=["Dockerfile"],
    )


def test_restart_only_refuses_stale_catalog_image_entrypoint(monkeypatch):
    from deployments.celery.helpers import DeploymentHelper

    service = SimpleNamespace(
        pk="service-1",
        deployed_at=SimpleNamespace(),
        source_kind="catalog",
        active_revision=SimpleNamespace(
            pk="revision-current",
            activated_at=None,
            config_snapshot={"source_kind": "catalog"},
            build_snapshot={
                "dockerfile": (
                    "FROM wordpress:7.1.2-php8.4-apache\n"
                    'ENTRYPOINT ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh"]\n'
                    'CMD ["apache2-foreground"]\n'
                )
            },
        ),
    )
    deploy = SimpleNamespace(
        service=service,
        revision_id="revision-current",
        updated_file_at=None,
    )

    container = MagicMock()
    container.exists.return_value = True
    container.get_image_identifier.return_value = "sha256:old"
    client_container = MagicMock()
    client_container.image.attrs = {
        "Config": {
            "Entrypoint": None,
            "Labels": {"io.passdeployer.revision": "revision-current"},
        }
    }
    container.client.containers.get.return_value = client_container

    monkeypatch.setattr("deployments.celery.helpers.Container", lambda name: container)
    monkeypatch.setattr("deployments.celery.helpers.Image.check_exists", lambda image: True)

    assert DeploymentHelper.is_restart_only(deploy, "wordpress") is False


def test_restart_only_accepts_current_catalog_image(monkeypatch):
    from deployments.celery.helpers import DeploymentHelper

    service = SimpleNamespace(
        pk="service-1",
        deployed_at=SimpleNamespace(),
        source_kind="catalog",
        active_revision=SimpleNamespace(
            pk="revision-current",
            activated_at=None,
            config_snapshot={"source_kind": "catalog"},
            build_snapshot={
                "dockerfile": (
                    "FROM wordpress:7.1.2-php8.4-apache\n"
                    'ENTRYPOINT ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh"]\n'
                    'CMD ["apache2-foreground"]\n'
                )
            },
        ),
    )
    deploy = SimpleNamespace(
        service=service,
        revision_id="revision-current",
        updated_file_at=None,
    )

    container = MagicMock()
    container.exists.return_value = True
    container.get_image_identifier.return_value = "sha256:current"
    client_container = MagicMock()
    client_container.image.attrs = {
        "Config": {
            "Entrypoint": ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh"],
            "Labels": {"io.passdeployer.revision": "revision-current"},
        }
    }
    container.client.containers.get.return_value = client_container

    monkeypatch.setattr("deployments.celery.helpers.Container", lambda name: container)
    monkeypatch.setattr("deployments.celery.helpers.Image.check_exists", lambda image: True)

    assert DeploymentHelper.is_restart_only(deploy, "wordpress") is True


def test_swarm_process_graph_does_not_resurrect_catalog_entrypoint_override(monkeypatch):
    from deployments.core.swarm import SwarmRuntime
    from deployments.core.types import DeploymentConfig

    config = DeploymentConfig(
        name="wordpress-service",
        tag="1.00",
        zip_path="/tmp/wordpress.zip",
        dockerfile_template=(
            "FROM wordpress:7.1.2-php8.4-apache\n"
            'ENTRYPOINT ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh"]\n'
            'CMD ["apache2-foreground"]\n'
        ),
        max_cpu=1.0,
        max_ram=512,
        networks=[],
        volumes=[],
        port=80,
        read_only=False,
        platform="docker",
        platform_type="APP",
        entry_point="/usr/local/bin/docker-entrypoint.sh",
        runtime_options={
            "catalog_managed": True,
            "processes": [{
                "name": "web",
                "process_type": "application",
                "command": "apache2-foreground",
                "entrypoint": None,
                "replicas": 1,
                "enabled": True,
            }],
        },
        labels={"service.id": "service-1"},
    )

    runtime = object.__new__(SwarmRuntime)
    runtime._last_apply_operation = None
    runtime._last_apply_recovery = {}
    runtime.service_names_for_service = lambda service_id: []
    runtime.assert_active = lambda: None

    captured = {}

    def fake_apply(process_config, **kwargs):
        captured["config"] = process_config
        return SimpleNamespace(replicas_running=1)

    runtime.apply = fake_apply
    result = runtime.apply_processes(
        config,
        image_ref="registry/wordpress:1.00",
        operation_key="deploy:1",
    )

    assert "web" in result
    assert captured["config"].entry_point is None
    assert captured["config"].start_command == "apache2-foreground"


def test_legacy_catalog_revision_drops_dockerfile_owned_process_entrypoint():
    from deployments.core.runtime_graph import ServiceRuntimeGraph

    # Reproduce the legacy auto-detected value that bypassed the catalog bootstrap.
    # Docker/Apache detection reports the image CMD as "apache2-foreground".
    stale_entrypoint = "apache2-foreground"
    revision = SimpleNamespace(
        pk="revision-1",
        config_snapshot={"source_kind": "catalog"},
        build_snapshot={
            "dockerfile": (
                "FROM wordpress:7.1.2-php8.4-apache\n"
                f'ENTRYPOINT ["{stale_entrypoint}"]\n'
                'CMD ["apache2-foreground"]\n'
            )
        },
        runtime_snapshot={},
        process_snapshot=[
            {
                "name": "web",
                "process_type": "application",
                "command": "apache2-foreground",
                "entrypoint": stale_entrypoint,
                "replicas": 1,
                "enabled": True,
            }
        ],
        environment_snapshot={},
        source_snapshot={},
        endpoint_snapshot=[],
        volume_snapshot=[],
        network_snapshot=[],
        revision_number=1,
    )

    graph = ServiceRuntimeGraph.from_revision(revision)

    assert graph.processes[0].command == "apache2-foreground"
    assert graph.processes[0].entrypoint is None


def test_catalog_profile_removes_stale_dockerfile_entrypoint_override():
    from deployments.common.deployment_profile import normalize_profile

    stale_entrypoint = "/usr/local/bin/passdeployer-wordpress-entrypoint.sh"
    dockerfile = (
        "FROM wordpress:7.1.2-php8.4-apache\n"
        f'ENTRYPOINT ["{stale_entrypoint}"]\n'
        'CMD ["apache2-foreground"]\n'
    )
    normalized = normalize_profile(
        {
            "source_kind": "catalog",
            "dockerfile": dockerfile,
            "entry_point": stale_entrypoint,
            "start_command": "apache2-foreground",
        }
    )

    assert normalized["runtime_options"]["catalog_managed"] is True
    assert normalized.get("entry_point") is None
    assert normalized["runtime_options"].get("entry_point") is None
    assert normalized["start_command"] == "apache2-foreground"


def test_catalog_dockerfile_entrypoint_survives_renderer(monkeypatch):
    from deployments.core import dockerfile

    monkeypatch.setattr(dockerfile, "check_requirements_txt", lambda *args, **kwargs: None)
    monkeypatch.setattr(dockerfile, "check_package_json", lambda *args, **kwargs: None)

    stale_entrypoint = "/usr/local/bin/passdeployer-wordpress-entrypoint.sh"
    config = DeploymentConfig(
        name="blog-wordpress-docker",
        tag="1.00",
        zip_path="/tmp/wordpress.zip",
        dockerfile_template=(
            "FROM wordpress:7.1.2-php8.4-apache\n"
            f'ENTRYPOINT ["{stale_entrypoint}"]\n'
            'CMD ["apache2-foreground"]\n'
        ),
        max_cpu=1.0,
        max_ram=512,
        networks=[],
        volumes=[],
        port=80,
        read_only=False,
        platform="docker",
        platform_type="APP",
        entry_point=stale_entrypoint,
        runtime_options={"catalog_managed": True},
    )

    rendered = dockerfile.DockerfileGenerator().render(
        platform="docker",
        dockerfile_template=config.dockerfile_template,
        tar_stream=io.BytesIO(b""),
        config=config,
    )

    # Regression: a stale compatibility entry_point must not make the generic
    # renderer strip the Dockerfile-owned ENTRYPOINT/CMD.
    assert f'ENTRYPOINT ["{stale_entrypoint}"]' in rendered
    assert 'CMD ["apache2-foreground"]' in rendered


def test_non_catalog_docker_entrypoint_still_overrides_dockerfile_cmd(monkeypatch):
    from deployments.core import dockerfile

    monkeypatch.setattr(dockerfile, "check_requirements_txt", lambda *args, **kwargs: None)
    monkeypatch.setattr(dockerfile, "check_package_json", lambda *args, **kwargs: None)

    config = DeploymentConfig(
        name="generic-docker",
        tag="1.00",
        zip_path="/tmp/generic.zip",
        dockerfile_template=(
            "FROM alpine:latest\n"
            'ENTRYPOINT ["/bin/sh", "-c"]\n'
            'CMD ["sleep infinity"]\n'
        ),
        max_cpu=1.0,
        max_ram=512,
        networks=[],
        volumes=[],
        port=80,
        read_only=False,
        platform="docker",
        platform_type="APP",
        entry_point="sleep 42",
        runtime_options={},
    )

    rendered = dockerfile.DockerfileGenerator().render(
        platform="docker",
        dockerfile_template=config.dockerfile_template,
        tar_stream=io.BytesIO(b""),
        config=config,
    )

    assert "ENTRYPOINT" not in rendered
    assert 'CMD ["sleep", "42"]' in rendered


def test_catalog_managed_docker_does_not_promote_detected_default_command(monkeypatch):
    from deployments.core.platforms.registry import PlatformRegistry
    from deployments.core import project_model

    monkeypatch.setattr(
        PlatformRegistry,
        "detect",
        lambda *args, **kwargs: (
            None,
            _detection(),
            _project_cfg(),
        ),
    )
    monkeypatch.setattr(
        "deployments.core.platform_bridge._ensure_plugins_loaded",
        lambda: None,
    )
    monkeypatch.setattr(
        "deployments.core.platform_bridge._project_file_index",
        lambda project_root: {},
    )
    monkeypatch.setattr(
        project_model,
        "build_project_model_from_tree",
        lambda *args, **kwargs: SimpleNamespace(applications=(), frontends=()),
    )

    config = DeploymentConfig(
        name="blog-wordpress-docker",
        tag="1.00",
        zip_path="/tmp/wordpress.zip",
        dockerfile_template=(
            "FROM wordpress:latest\n"
            'ENTRYPOINT ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh"]\n'
            'CMD ["apache2-foreground"]\n'
        ),
        max_cpu=1.0,
        max_ram=512,
        networks=[],
        volumes=[],
        port=80,
        read_only=False,
        platform="docker",
        platform_type="APP",
        runtime_options={"catalog_managed": True, "processes": []},
    )

    enriched = enrich_config_from_project(config, "/tmp")

    assert enriched.start_command == "apache2-foreground"
    assert enriched.entry_point is None


def test_non_catalog_docker_still_promotes_detected_default_command(monkeypatch):
    from deployments.core.platforms.registry import PlatformRegistry
    from deployments.core import project_model

    monkeypatch.setattr(
        PlatformRegistry,
        "detect",
        lambda *args, **kwargs: (
            None,
            _detection(),
            _project_cfg(),
        ),
    )
    monkeypatch.setattr(
        "deployments.core.platform_bridge._ensure_plugins_loaded",
        lambda: None,
    )
    monkeypatch.setattr(
        "deployments.core.platform_bridge._project_file_index",
        lambda project_root: {},
    )
    monkeypatch.setattr(
        project_model,
        "build_project_model_from_tree",
        lambda *args, **kwargs: SimpleNamespace(applications=(), frontends=()),
    )

    config = DeploymentConfig(
        name="generic-docker",
        tag="1.00",
        zip_path="/tmp/app.zip",
        dockerfile_template='FROM alpine:latest\nCMD ["sleep", "infinity"]\n',
        max_cpu=1.0,
        max_ram=512,
        networks=[],
        volumes=[],
        port=80,
        read_only=False,
        platform="docker",
        platform_type="APP",
        runtime_options={},
    )

    enriched = enrich_config_from_project(config, "/tmp")

    assert enriched.entry_point == "apache2-foreground"
    