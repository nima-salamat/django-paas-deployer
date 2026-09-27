from unittest.mock import Mock, patch

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
            {
                "Name": "vol-demo-data",
                "UsageData": {"Size": used_bytes, "RefCount": 1},
            }
        ]
    }
    return client


def test_volume_usage_thresholds_are_based_on_actual_bytes():
    from deployments.core.volume_storage import (
        USAGE_CRITICAL,
        USAGE_NORMAL,
        USAGE_WARNING,
        inspect_volume_usage,
    )
    mb = 1024 * 1024
    assert inspect_volume_usage(_client(int(89.9 * mb)), "vol-demo-data", 100, threshold_percent=90).usage_state == USAGE_NORMAL
    assert inspect_volume_usage(_client(90 * mb), "vol-demo-data", 100, threshold_percent=90).usage_state == USAGE_WARNING
    assert inspect_volume_usage(_client(95 * mb), "vol-demo-data", 100, threshold_percent=90).usage_state == USAGE_WARNING
    assert inspect_volume_usage(_client(100 * mb), "vol-demo-data", 100, threshold_percent=90).usage_state == USAGE_CRITICAL
    assert inspect_volume_usage(_client(101 * mb), "vol-demo-data", 100, threshold_percent=90).usage_state == USAGE_CRITICAL


def test_unknown_docker_usage_is_not_reported_as_zero():
    from deployments.core.volume_storage import USAGE_UNKNOWN, inspect_volume_usage
    client = _client(-1)
    usage = inspect_volume_usage(client, "vol-demo-data", 100)
    assert usage.usage_state == USAGE_UNKNOWN
    assert usage.actual_used_bytes is None


def test_local_volume_capability_is_not_hard_enforced():
    from deployments.core.volume_storage import CAPACITY_LOGICAL_ONLY, storage_capabilities
    capabilities = storage_capabilities("local", "local")
    assert capabilities.capacity_mode == CAPACITY_LOGICAL_ONLY
    assert capabilities.supports_hard_capacity is False
    assert capabilities.supports_resize is False


def test_volume_save_serializes_logical_quota_against_service_row():
    user = User.objects.create_user(username="quota-lock", password="test-password")
    plan = Plan.objects.create(name="Quota", platform="django", max_cpu=1, max_ram=512, max_storage=1, price_per_hour=0)
    service = Service.objects.create(name="quota-service", user=user, plan=plan)
    with patch.object(Volume, "full_clean", autospec=True) as clean, patch.object(Volume._meta.concrete_model.__mro__[1], "save", autospec=True):
        volume = Volume(name="quota-data", user=user, service=service, size_mb=512, default_bind="/data")
        volume.save()
    assert clean.called
    assert Volume.objects.filter(service=service).count() == 1


class PersistentAutoVolumeContractTests(TestCase):
    @override_settings(SWARM_ENABLED=False)
    def test_default_application_volume_is_registry_backed(self):
        user = User.objects.create_user(username="auto-volume", password="test-password")
        plan = Plan.objects.create(name="Auto", platform="django", max_cpu=1, max_ram=512, max_storage=2, price_per_hour=0)
        service = Service.objects.create(name="auto-service", user=user, plan=plan)
        from deployments.core.volumes import VolumeMountManager
        manager = VolumeMountManager()
        specs = manager.ensure_default_volumes([], platform="django", service_name="auto-service", service_id=str(service.pk))
        row = Volume.objects.get(service=service)
        assert specs[0].source == row.get_docker_volume_name()
        assert row.size_mb == specs[0].size_mb

    def test_default_application_volume_without_service_identity_fails(self):
        from deployments.core.volumes import VolumeMountManager
        from deployments.common.exceptions import VolumeError
        import pytest
        with pytest.raises(VolumeError):
            VolumeMountManager().ensure_default_volumes([], platform="django", service_name="anonymous")

def test_logical_quota_rejects_second_allocation():
    user = User.objects.create_user(username="quota-second", password="test-password")
    plan = Plan.objects.create(name="Quota2", platform="django", max_cpu=1, max_ram=512, max_storage=1, price_per_hour=0)
    service = Service.objects.create(name="quota-service-2", user=user, plan=plan)
    first = Volume.objects.create(name="quota-a", user=user, service=service, size_mb=800, default_bind="/a")
    assert first.service_id == service.pk
    from django.core.exceptions import ValidationError
    second = Volume(name="quota-b", user=user, service=service, size_mb=300, default_bind="/b")
    with __import__("pytest").raises(ValidationError):
        second.save()


def test_volume_save_uses_service_row_lock():
    from core.base.BaseModel import BaseModel
    from unittest.mock import Mock, patch

    user = User.objects.create_user(username="quota-lock-source", password="test-password")
    plan = Plan.objects.create(name="QuotaLock", platform="django", max_cpu=1, max_ram=512, max_storage=1, price_per_hour=0)
    service = Service.objects.create(name="quota-lock-service", user=user, plan=plan)
    locked = Mock(pk=service.pk)
    locked.can_allocate_storage.return_value = (True, "")
    volume = Volume(name="quota-lock-volume", user=user, service=service, size_mb=128, default_bind="/data")
    with patch.object(type(Service.objects), "select_for_update", return_value=Mock(get=Mock(return_value=locked))), patch.object(Volume, "full_clean", return_value=None), patch.object(BaseModel, "save", return_value=None):
        volume.save()
    assert locked.can_allocate_storage.called


def test_managed_auto_volume_has_single_registry_identity():
    user = User.objects.create_user(username="managed-auto", password="test-password")
    plan = Plan.objects.create(name="Managed", platform="django", max_cpu=1, max_ram=512, max_storage=2, price_per_hour=0)
    service = Service.objects.create(name="managed-auto-service", user=user, plan=plan)
    from deployments.core.volumes import VolumeMountManager
    manager = VolumeMountManager()
    specs = manager.ensure_default_volumes([], platform="python", service_name=service.name, service_id=str(service.pk))
    assert len(specs) == 1
    row = Volume.objects.get(service=service, default_bind="/app/data")
    assert specs[0].source == row.get_docker_volume_name()
    assert specs[0].size_mb == row.size_mb