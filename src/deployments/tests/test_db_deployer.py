from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from deployments.core.db_deployer import DBDeployer


def test_ready_app_database_deploy_propagates_application_identity_labels():
    runtime = MagicMock()
    runtime.apply_external_image_service.return_value = SimpleNamespace(
        service_id="swarm-service",
        replicas_running=1,
    )

    cfg = {
        "application_instance": "app-123",
        "catalog_service_key": "mariadb",
        "max_cpu": 1.0,
        "max_ram": 512,
        "username": "app",
        "password": "secret",
        "root_password": "root-secret",
        "database": "wordpress",
    }

    with patch("deployments.core.db_deployer.SwarmRuntime", return_value=runtime):
        result = DBDeployer()._deploy_swarm_database(
            service_id="svc-123",
            container_name="app-svc123-mariadb-mariadb",
            platform="redis",
            full_image="redis:7-alpine",
            environment={},
            command=None,
            networks=["net-app123"],
            volume_binds={},
            target_port=6379,
            published_port=None,
            host_port=None,
            cfg=cfg,
            force_reinit=False,
            deployment_id="dep-123",
            log=MagicMock(),
            registry_volume_rows={},
        )

    assert result.success is True
    kwargs = runtime.apply_external_image_service.call_args.kwargs
    assert kwargs["labels"]["application.id"] == "app-123"
    assert kwargs["labels"]["application.service"] == "mariadb"
    assert kwargs["labels"]["passdeployer.process"] == "database"
