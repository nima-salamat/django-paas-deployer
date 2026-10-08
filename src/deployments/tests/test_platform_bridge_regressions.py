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


def test_revision_build_files_are_preserved_in_execution_config():
    from deployments.celery.services.deploy_service import _preserve_revision_build_files

    revision_snapshot = {
        "source_kind": "catalog",
        "build": {
            "dockerfile": (
                "FROM wordpress:7.1.2-php8.4-apache\n"
                'COPY passdeployer-wordpress-entrypoint.sh /usr/local/bin/passdeployer-wordpress-entrypoint.sh\n'
            ),
            "files": {
                "passdeployer-wordpress-entrypoint.sh": "#!/bin/sh\nset -eu\n",
            },
        },
    }

    result = _preserve_revision_build_files(
        {"secure_docker_source": True},
        revision_snapshot,
    )

    assert result["secure_docker_source"] is True
    assert result["revision_build_files"] == {
        "passdeployer-wordpress-entrypoint.sh": "#!/bin/sh\nset -eu\n",
    }


def test_revision_build_files_are_not_added_for_non_catalog_revisions():
    from deployments.celery.services.deploy_service import _preserve_revision_build_files

    result = _preserve_revision_build_files(
        {"secure_docker_source": True},
        {
            "source_kind": "dockerfile",
            "build": {
                "files": {
                    "script.sh": "#!/bin/sh\n",
                },
            },
        },
    )

    assert result == {"secure_docker_source": True}

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


def test_legacy_catalog_revision_drops_stale_process_command_when_catalog_does_not_define_one():
    from deployments.core.runtime_graph import ServiceRuntimeGraph

    revision = SimpleNamespace(
        pk="revision-wordpress-legacy",
        config_snapshot={"source_kind": "catalog"},
        build_snapshot={
            "dockerfile": (
                "FROM wordpress:7.1.2-php8.4-apache\n"
                'ENTRYPOINT ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh"]\n'
                'CMD ["apache2-foreground"]\n'
            ),
        },
        runtime_snapshot={
            "start_command": None,
            "entry_point": None,
        },
        process_snapshot=[{
            "name": "web",
            "process_type": "application",
            "command": "true",
            "entrypoint": "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
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

    assert graph.processes[0].command == "/usr/local/bin/passdeployer-wordpress-entrypoint.sh apache2-foreground"
    assert graph.processes[0].entrypoint is None
    assert graph.execution_contract.entrypoint_source == "IMAGE"
    assert graph.execution_contract.args == (
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
        "apache2-foreground",
    )

def test_legacy_catalog_revision_drops_dockerfile_owned_process_overrides():
    from deployments.core.runtime_graph import ServiceRuntimeGraph

    # Reproduce the legacy auto-detected process values that bypassed the
    # catalog bootstrap. The catalog itself declares no runtime command, so
    # both process-level overrides must be removed and Docker's image metadata
    # must supply the executable.
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
        runtime_snapshot={
            "start_command": None,
            "entry_point": None,
        },
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
    assert graph.execution_contract.entrypoint_source == "IMAGE"
    assert graph.execution_contract.args == ("apache2-foreground",)


def test_catalog_revision_ignores_stale_stored_execution_contract():
    from deployments.core.runtime_graph import ServiceRuntimeGraph

    revision = SimpleNamespace(
        pk="revision-stale-contract",
        config_snapshot={"source_kind": "catalog"},
        build_snapshot={
            "dockerfile": (
                "FROM wordpress:7.1.2-php8.4-apache\n"
                'ENTRYPOINT ["/usr/local/bin/docker-ensure-installed.sh"]\n'
                'CMD ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh", "apache2-foreground"]\n'
            )
        },
        runtime_snapshot={
            "start_command": "docker-entrypoint.sh apache2-foreground",
            "entry_point": None,
        },
        process_snapshot=[
            {
                "name": "web",
                "process_type": "application",
                "command": "docker-entrypoint.sh apache2-foreground",
                "entrypoint": None,
                "replicas": 1,
                "enabled": True,
                "execution_contract": {
                    "entrypoint_source": "IMAGE",
                    "image_entrypoint": ["docker-entrypoint.sh"],
                    "image_cmd": ["apache2-foreground"],
                    "command": None,
                    "args": ["apache2-foreground"],
                    "catalog_managed": True,
                    "image_entrypoint_owned": True,
                    "process_name": "web",
                    "contract_version": "1",
                    "required_executables": [],
                    "source_kind": "catalog",
                },
            }
        ],
        environment_snapshot={},
        source_snapshot={"catalog_id": "wordpress"},
        endpoint_snapshot=[],
        volume_snapshot=[],
        network_snapshot=[],
        revision_number=1,
    )

    graph = ServiceRuntimeGraph.from_revision(revision)

    assert graph.execution_contract.entrypoint_source == "IMAGE"
    assert graph.execution_contract.image_entrypoint == ("/usr/local/bin/docker-ensure-installed.sh",)
    assert graph.execution_contract.args == (
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
        "apache2-foreground",
    )

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


def test_docker_source_process_override_ignores_stale_compatibility_start_command():
    from deployments.celery.services.deploy_service import (
        _apply_explicit_docker_source_process_override,
    )

    cfg = {
        "start_command": "true",
        "processes": [{
            "name": "web",
            "process_type": "web",
            "command": None,
            "entrypoint": None,
            "replicas": 1,
            "enabled": True,
            "environment": {},
        }],
    }
    runtime_options = {"processes": list(cfg["processes"])}

    _apply_explicit_docker_source_process_override(
        cfg,
        runtime_options,
        {"source_kind": "dockerfile"},
    )

    assert cfg["processes"][0]["command"] is None
    assert runtime_options["processes"][0]["command"] is None
    assert cfg["start_command"] == "true"


def test_docker_source_process_override_uses_explicit_source_command():
    from deployments.celery.services.deploy_service import (
        _apply_explicit_docker_source_process_override,
    )

    cfg = {"start_command": "true"}
    runtime_options = {}
    _apply_explicit_docker_source_process_override(
        cfg,
        runtime_options,
        {"command": "apache2-foreground"},
    )

    assert cfg["processes"][0]["command"] == "apache2-foreground"
    assert runtime_options["processes"][0]["command"] == "apache2-foreground"

def test_native_catalog_entrypoint_contract_sets_renderer_identity():
    from deployments.celery.services.deploy_service import (
        _enforce_catalog_dockerfile_entrypoint_contract,
    )

    cfg = {"entry_point": "/usr/local/bin/passdeployer-wordpress-entrypoint.sh"}
    runtime_options = {
        "processes": [{
            "name": "web",
            "command": "apache2-foreground",
            "entrypoint": None,
            "replicas": 1,
            "enabled": True,
        }]
    }
    dockerfile = (
        "FROM wordpress:7.1.2-php8.4-apache\n"
        'ENTRYPOINT ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh"]\n'
        'CMD ["apache2-foreground"]\n'
    )

    entry_point = _enforce_catalog_dockerfile_entrypoint_contract(
        cfg,
        runtime_options,
        source_kind="catalog",
        dockerfile_text=dockerfile,
        entry_point=cfg["entry_point"],
    )

    assert entry_point is None
    assert runtime_options["catalog_managed"] is True
    assert "entry_point" not in cfg
    assert "entry_point" not in runtime_options
    assert "entrypoint" not in runtime_options


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
    

def test_legacy_catalog_revision_infers_image_entrypoint_ownership():
    from deployments.core.runtime_graph import ServiceRuntimeGraph

    revision = SimpleNamespace(
        pk="revision-legacy-catalog",
        config_snapshot={},
        source_snapshot={"catalog_id": "wordpress", "service_key": "wordpress"},
        build_snapshot={
            "dockerfile": (
                "FROM wordpress:7.1.2-php8.4-apache\n"
                'ENTRYPOINT ["/usr/local/bin/docker-ensure-installed.sh"]\n'
                'CMD ["/usr/local/bin/passdeployer-wordpress-entrypoint.sh", "apache2-foreground"]\n'
            )
        },
        runtime_snapshot={"start_command": None, "entry_point": None},
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
        revision_number=1,
    )

    graph = ServiceRuntimeGraph.from_revision(revision)

    assert graph.runtime["catalog_managed"] is True
    assert graph.runtime["image_entrypoint_owned"] is True
    assert graph.processes[0].entrypoint is None
    assert graph.processes[0].command == (
        "/usr/local/bin/passdeployer-wordpress-entrypoint.sh apache2-foreground"
    )


def test_catalog_revision_refresh_is_requested_when_build_files_are_missing():
    from services.revisioning import _catalog_revision_requires_refresh

    service = SimpleNamespace(
        source_kind="catalog",
        build_config={
            "files": {
                "passdeployer-wordpress-entrypoint.sh": "#!/bin/sh\n"
            }
        },
    )
    revision = SimpleNamespace(
        config_snapshot={"source_kind": "catalog"},
        build_snapshot={"dockerfile": "FROM wordpress:latest\n"},
    )

    assert _catalog_revision_requires_refresh(service, revision) is True


def test_complete_catalog_revision_does_not_trigger_compatibility_refresh():
    from services.revisioning import _catalog_revision_requires_refresh

    service = SimpleNamespace(
        source_kind="catalog",
        build_config={
            "files": {
                "passdeployer-wordpress-entrypoint.sh": "#!/bin/sh\n"
            }
        },
    )
    revision = SimpleNamespace(
        config_snapshot={"source_kind": "catalog"},
        build_snapshot={
            "dockerfile": "FROM wordpress:latest\n",
            "files": {
                "passdeployer-wordpress-entrypoint.sh": "#!/bin/sh\n"
            },
        },
    )

    assert _catalog_revision_requires_refresh(service, revision) is False
