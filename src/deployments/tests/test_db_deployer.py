from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from deployments.core.db_deployer import DBDeployer




def test_image_pull_failure_is_user_friendly_and_retryable_for_mirror_dns_timeout():
    from deployments.core.db_deployer import _format_image_pull_failure

    class MirrorDnsTimeout(Exception):
        status_code = 500

    exc = MirrorDnsTimeout(
        '500 Server Error: failed to resolve reference "docker.arvancloud.ir/mariadb:11": '
        'dial tcp: lookup docker.arvancloud.ir on 127.0.0.53:53: i/o timeout'
    )
    message, details = _format_image_pull_failure(
        "docker.arvancloud.ir/mariadb:11",
        exc,
    )

    assert "could not reach" in message.lower()
    assert "dns/network" in message.lower()
    assert "retry" in message.lower()
    assert details["retryable"] is True
    assert details["reason_code"] == "transient_http"
    assert "technical_error" in details


def test_db_deploy_retry_path_allows_same_owned_celery_task_to_resume_running_deploy():
    from pathlib import Path
    import inspect
    from deployments.celery.tasks import _lock_for_db_deploy, run_db_deploy

    source = inspect.getsource(_lock_for_db_deploy)
    task_source = inspect.getsource(run_db_deploy)
    assert "allow_owned_retry" in source
    assert "owned_retry" in source
    assert "allow_owned_retry=bool(getattr(self.request, \"retries\", 0))" in task_source
    assert "result_details.get(\"retryable\")" in task_source
    assert "self.retry(exc=retry_error" in task_source


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
