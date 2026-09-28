from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from plans.models import Plan
from services.models import Service, Volume
from users.models import User


class _FakeVolume:
    def __init__(self, attrs=None):
        self.attrs = attrs or {"Driver": "local", "Scope": "local"}


def _client(used_bytes):
    client = Mock()
    client.volumes.get.return_value = _FakeVolume()
    client.df.return_value = {
        "VolumesUsage": [
            {"Name": "vol-demo-data", "UsageData": {"Size": used_bytes, "RefCount": 1}}
        ]
    }
    return client


def test_volume_usage_thresholds_are_based_on_actual_bytes():
    from deployments.core.volume_storage import USAGE_CRITICAL, USAGE_NORMAL, USAGE_WARNING, inspect_volume_usage
    mb = 1024 * 1024
    assert inspect_volume_usage(_client(int(89.9 * mb)), "vol-demo-data", 100, threshold_percent=90).usage_state == USAGE_NORMAL
    assert inspect_volume_usage(_client(90 * mb), "vol-demo-data", 100, threshold_percent=90).usage_state == USAGE_WARNING
    assert inspect_volume_usage(_client(95 * mb), "vol-demo-data", 100, threshold_percent=90).usage_state == USAGE_WARNING
    assert inspect_volume_usage(_client(100 * mb), "vol-demo-data", 100, threshold_percent=90).usage_state == USAGE_CRITICAL
    assert inspect_volume_usage(_client(101 * mb), "vol-demo-data", 100, threshold_percent=90).usage_state == USAGE_CRITICAL


def test_unknown_docker_usage_is_not_reported_as_zero():
    from deployments.core.volume_storage import USAGE_UNKNOWN, inspect_volume_usage
    usage = inspect_volume_usage(_client(-1), "vol-demo-data", 100)
    assert usage.usage_state == USAGE_UNKNOWN
    assert usage.actual_used_bytes is None


def test_local_volume_capability_is_not_hard_enforced():
    from deployments.core.volume_storage import CAPACITY_LOGICAL_ONLY, storage_capabilities
    capabilities = storage_capabilities("local", "local")
    assert capabilities.capacity_mode == CAPACITY_LOGICAL_ONLY
    assert capabilities.supports_hard_capacity is False
    assert capabilities.supports_resize is False


def test_logical_quota_helpers_preserve_declared_allocation_semantics():
    from unittest.mock import patch

    service = Service(plan=Plan(max_storage=1))
    with patch("services.models.Volume.objects.filter") as filter_mock:
        filter_mock.return_value.distinct.return_value.aggregate.return_value = {"s": 800}
        assert Service.get_storage_quota_mb(service) == 1024
        assert Service.get_used_storage_mb(service) == 800
        assert Service.get_remaining_storage_mb(service) == 224
        ok, _ = Service.can_allocate_storage(service, 224)
        assert ok is True
        ok, message = Service.can_allocate_storage(service, 225)
        assert ok is False
        assert "remaining 224 MB" in message


def test_volume_save_serializes_quota_with_service_row_lock():
    source = __import__("inspect").getsource(Volume.save)
    assert "select_for_update" in source
    assert "transaction.atomic" in source


def test_volume_clean_routes_quota_through_service_rule():
    source = __import__("inspect").getsource(Volume.clean)
    assert "can_allocate_storage" in source
    assert "exclude_volume_id=self.pk" in source


def test_volume_resize_guard_rejects_provisioned_backend_without_resize():
    source = __import__("inspect").getsource(Volume.clean)
    assert "supports_resize" in source
    assert "backing Docker volume" in source


def test_managed_auto_volume_requires_service_identity():
    from deployments.core.volumes import VolumeMountManager
    from deployments.core.exceptions import VolumeError
    with __import__("pytest").raises(VolumeError):
        VolumeMountManager().ensure_default_volumes([], platform="python", service_name="anonymous")

def test_volume_warning_uses_existing_deployment_event_pipeline():
    from deployments.core.types import VolumeSpec
    from deployments.core.volumes import VolumeMountManager
    from deployments.core import volume_storage

    logger = Mock()
    usage = volume_storage.VolumeUsage(
        volume="vol-demo-data",
        declared_capacity_bytes=100 * 1024 * 1024,
        actual_used_bytes=92 * 1024 * 1024,
        usage_percent=92.0,
        usage_state=volume_storage.USAGE_WARNING,
        threshold_percent=90.0,
        driver="local",
        scope="local",
        enforced=False,
        capacity_mode=volume_storage.CAPACITY_LOGICAL_ONLY,
        usage_available=True,
    )
    with patch("deployments.core.manager.client_manager.Client") as client_cls, patch("deployments.core.volume_storage.inspect_volume_usage", return_value=usage), patch("deployments.core.volume_storage.usage_details", return_value={"volume": "vol-demo-data", "declared_mb": 100, "used_mb": 92, "usage_percent": 92.0, "threshold_percent": 90.0, "usage_state": "warning", "driver": "local", "scope": "local", "enforced": False, "capacity_mode": "LOGICAL_ONLY", "usage_available": True, "error": None}):
        client_cls.return_value.client = Mock()
        manager = VolumeMountManager(logger=logger)
        manager.warn_about_usage([VolumeSpec(source="vol-demo-data", target="/data", size_mb=100)])
    logger.warning.assert_called_once()
    args, kwargs = logger.warning.call_args
    assert args[0] == "volume_creation"
    assert "92.0% full" in args[1]
    assert kwargs["details"]["usage_state"] == "warning"

def test_volume_usage_reconciliation_detects_docker_orphan_and_missing_registry_volume():
    from deployments.core.volume_storage import reconcile_managed_volumes
    from unittest.mock import patch

    class DockerRow:
        def __init__(self, name):
            self.name = name
            self.attrs = {
                "Name": name,
                "Labels": {"managed-by": "django-paas-deployer"},
            }

    db_id = "12345678-1234-1234-1234-123456789abc"
    manager = Mock()
    manager.volumes.list.return_value = [
        DockerRow("vol-12345678-db-data"),
        DockerRow("vol-orphan-unregistered"),
    ]
    registry_rows = [
        {"id": db_id, "name": "db-data", "service_id": "svc-1", "size_mb": 1024, "released_at": None},
        {"id": "87654321-1234-1234-1234-123456789abc", "name": "app-data", "service_id": "svc-2", "size_mb": 512, "released_at": None},
    ]
    with patch("services.models.Volume.objects.values", return_value=registry_rows):
        result = reconcile_managed_volumes(manager)
    assert [row["volume"] for row in result["docker_orphans"]] == ["vol-orphan-unregistered"]
    assert [row["volume"] for row in result["missing_docker"]] == ["vol-87654321-app-data"]


def test_db_volume_resolution_requires_registry_identity():
    from deployments.core.db_deployer import _registered_volume_for_service
    from deployments.core.exceptions import DeploymentError
    row = Mock(size_mb=1024)
    row.get_docker_volume_name.return_value = "vol-db-canonical"
    with patch("services.models.Volume.objects.filter", return_value=[row]):
        assert _registered_volume_for_service("vol-db-canonical", "svc-1") is row
    with patch("services.models.Volume.objects.filter", return_value=[]):
        with __import__("pytest").raises(DeploymentError):
            _registered_volume_for_service("vol-unregistered", "svc-1")


def test_db_deployer_named_volume_path_is_registry_backed():
    from deployments.core.db_deployer import DBDeployer
    source = __import__("inspect").getsource(DBDeployer.deploy)
    assert "_registered_volume_for_service" in source
    assert "DockerVolume(" in source
    assert "client.volumes.create(" not in source

def test_volume_usage_handles_missing_volume_and_docker_api_failure():
    from deployments.core.volume_storage import USAGE_UNKNOWN, inspect_volume_usage
    missing = Mock()
    missing.volumes.get.side_effect = RuntimeError("volume missing")
    usage = inspect_volume_usage(missing, "vol-missing", 100)
    assert usage.usage_state == USAGE_UNKNOWN
    assert usage.usage_available is False

    api_failure = Mock()
    api_failure.volumes.get.return_value = _FakeVolume()
    api_failure.df.side_effect = RuntimeError("docker api failed")
    usage = inspect_volume_usage(api_failure, "vol-api", 100)
    assert usage.usage_state == USAGE_UNKNOWN
    assert usage.actual_used_bytes is None


def test_volume_warning_at_100_uses_error_level_and_truthful_details():
    from deployments.core.types import VolumeSpec
    from deployments.core.volumes import VolumeMountManager
    from deployments.core import volume_storage
    logger = Mock()
    usage = volume_storage.VolumeUsage(
        volume="vol-full",
        declared_capacity_bytes=100 * 1024 * 1024,
        actual_used_bytes=101 * 1024 * 1024,
        usage_percent=101.0,
        usage_state=volume_storage.USAGE_CRITICAL,
        threshold_percent=90.0,
        driver="local",
        scope="local",
        enforced=False,
        capacity_mode=volume_storage.CAPACITY_LOGICAL_ONLY,
        usage_available=True,
    )
    with patch("deployments.core.volume_storage.inspect_volume_usage", return_value=usage), patch("deployments.core.volume_storage.usage_details", return_value={"volume": "vol-full", "declared_mb": 100, "used_mb": 101, "usage_percent": 101.0, "usage_state": "critical", "threshold_percent": 90.0, "driver": "local", "scope": "local", "enforced": False, "capacity_mode": "LOGICAL_ONLY", "usage_available": True, "error": None}), patch("deployments.core.manager.client_manager.Client") as client_cls:
        client_cls.return_value.client = Mock()
        VolumeMountManager(logger=logger).warn_about_usage([VolumeSpec(source="vol-full", target="/data", size_mb=100)])
    logger.error.assert_called_once()
    args, kwargs = logger.error.call_args
    assert args[0] == "volume_creation"
    assert "101.0%" in args[1]
    assert kwargs["details"]["capacity_mode"] == "LOGICAL_ONLY"
    assert kwargs["details"]["enforced"] is False


def test_bind_mount_is_not_reported_as_managed_volume_usage():
    from deployments.core.types import VolumeSpec
    from deployments.core.volumes import VolumeMountManager
    logger = Mock()
    with patch("deployments.core.manager.client_manager.Client") as client_cls, patch("deployments.core.volume_storage.inspect_volume_usage") as inspect:
        client_cls.return_value.client = Mock()
        VolumeMountManager(logger=logger).warn_about_usage([VolumeSpec(source="/srv/tenant", target="/data", mount_type="bind", size_mb=100)])
    inspect.assert_not_called()
    logger.warning.assert_not_called()
def test_release_transition_is_centralized_and_reclaimable():
    source = __import__("inspect").getsource(Volume.save)
    assert "previous_service_id" in source
    assert "self.released_at = self.released_at or timezone.now()" in source
    assert "reclaim_attempted_at" in source
    tasks = __import__("pathlib").Path(
        __file__).resolve().parents[2] / "deployments" / "celery" / "tasks.py"
    ).read_text(encoding="utf-8")
    assert "reclaim_released_volumes" in tasks
    assert "released_at__lte=cutoff" in tasks
