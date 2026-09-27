from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

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


@override_settings(DATABASES={
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
})
class StorageQuotaDatabaseTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = User.objects.create_user(username=f"quota-{self._testMethodName}", password="test-password")
        self.plan = Plan.objects.create(name=f"Quota-{self._testMethodName}", platform="django", max_cpu=1, max_ram=512, max_storage=1, price_per_hour=0)
        self.service = Service.objects.create(name=f"service-{self._testMethodName}", user=self.user, plan=self.plan)

    def test_logical_quota_rejects_second_allocation(self):
        Volume.objects.create(name="quota-a", user=self.user, service=self.service, size_mb=800, default_bind="/a")
        second = Volume(name="quota-b", user=self.user, service=self.service, size_mb=300, default_bind="/b")
        with self.assertRaises(ValidationError):
            second.save()

    def test_volume_resize_is_rejected_when_backend_volume_exists(self):
        volume = Volume.objects.create(name="quota-resize", user=self.user, service=self.service, size_mb=512, default_bind="/data")
        with patch("deployments.core.manager.volume_manager.Volume") as docker_volume:
            docker_volume.return_value.client.volumes.get.return_value = Mock(attrs={"Driver": "local", "Scope": "local"})
            volume.size_mb = 768
            with self.assertRaises(ValidationError):
                volume.save()

    def test_volume_save_contains_service_row_lock_boundary(self):
        source = __import__("inspect").getsource(Volume.save)
        assert "select_for_update" in source
        assert "transaction.atomic" in source

    def test_managed_auto_volume_has_single_registry_identity(self):
        from deployments.core.volumes import VolumeMountManager
        manager = VolumeMountManager()
        specs = manager.ensure_default_volumes([], platform="python", service_name=self.service.name, service_id=str(self.service.pk))
        self.assertEqual(len(specs), 1)
        row = Volume.objects.get(service=self.service, default_bind="/app/data")
        self.assertEqual(specs[0].source, row.get_docker_volume_name())
        self.assertEqual(specs[0].size_mb, row.size_mb)

    def test_default_volume_without_service_identity_fails(self):
        from deployments.core.volumes import VolumeMountManager
        from deployments.core.exceptions import VolumeError
        with self.assertRaises(VolumeError):
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
            self.attrs = {"Name": name}

    db_id = "12345678-1234-1234-1234-123456789abc"
    manager = Mock()
    manager.volumes.list.return_value = [
        DockerRow("vol-12345678-db-data"),
        DockerRow("vol-orphan-unregistered"),
    ]
    registry_rows = [
        {"id": db_id, "name": "db-data", "service_id": "svc-1", "size_mb": 1024},
        {"id": "87654321-1234-1234-1234-123456789abc", "name": "app-data", "service_id": "svc-2", "size_mb": 512},
    ]
    with patch("services.models.Volume.objects.values", return_value=registry_rows):
        result = reconcile_managed_volumes(manager)
    assert [row["volume"] for row in result["docker_orphans"]] == ["vol-orphan-unregistered"]
    assert [row["volume"] for row in result["missing_docker"]] == ["vol-87654321-app-data"]
