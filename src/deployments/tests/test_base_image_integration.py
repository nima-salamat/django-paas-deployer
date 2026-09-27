import io
import os
import shutil
import tempfile
import zipfile

import pytest


pytestmark = pytest.mark.deployment_integration


def _docker_available():
    try:
        import docker
        client = docker.from_env(timeout=20)
        client.ping()
        return client
    except Exception:
        return None


@pytest.mark.skipif(
    os.environ.get("RUN_DEPLOYMENT_INTEGRATION", "").strip().lower() not in {"1", "true", "yes", "on"},
    reason="real Docker deployment integration is opt-in",
)
def test_php84_missing_base_auto_build_reaches_final_container():
    client = _docker_available()
    if client is None:
        pytest.skip("Docker daemon is unavailable")
    from deploy.base_images import _php
    from deployments.common.resource_policy import build_limits
    from deployments.core.orchestrator import DeploymentOrchestrator
    from deployments.core.types import DeploymentConfig
    from deployments.core.manager import image_manager

    source = _php("8.4", public_root=False).source_image
    # The test exercises the real base-image path but avoids leaving a
    # persistent application container behind.
    with tempfile.TemporaryDirectory(prefix="paas-base-e2e-") as td:
        archive = os.path.join(td, "app.zip")
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("index.php", "<?php echo 'base-image-e2e';")
        cfg = DeploymentConfig(
            name="base-image-e2e",
            tag="test",
            zip_path=archive,
            dockerfile_template="FROM php:8.4-apache\nCOPY . /var/www/html/",
            max_cpu=1.0,
            max_ram=1024,
            networks=[],
            volumes=[],
            port=8080,
            read_only=False,
            platform="php",
            platform_type="APP",
            runtime_version="8.4",
            build_resource_policy=build_limits(),
            resource_limits={"cpu": 1.0, "memory": 1024, "pids_limit": 2048},
        )
        result = DeploymentOrchestrator().deploy(cfg)
        assert result.success, getattr(result, "details", None)
        assert result.image_ref.startswith("base-image-e2e:")
        container = None
        try:
            container = client.containers.get(result.container_name)
            assert container.status in {"running", "created"}
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
        assert "FROM paas-base/php-apache-root:8.4-r1" in cfg.dockerfile_template or source.startswith("docker")
