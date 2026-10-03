from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from plans.models import Plan
from services.models import PrivateNetwork, Service, Volume
from services.serializers import ServiceSerializer, VolumeSerializer

User = get_user_model()


class ServiceModelPolicyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="svc-owner", email="svc@example.com", password="password123")
        self.plan = Plan.objects.create(
            name="Bronze",
            platform="docker",
            plan_type="APP",
            max_cpu=1,
            max_ram=1024,
            max_storage=10,
            price_per_hour=10,
            storage_type="SSD",
        )
        self.plan2 = Plan.objects.create(
            name="Silver",
            platform="docker",
            plan_type="APP",
            max_cpu=2,
            max_ram=2048,
            max_storage=20,
            price_per_hour=20,
            storage_type="SSD",
        )
        self.network = PrivateNetwork.objects.create(user=self.user, name="svc-net")

    def make_service(self, **extra):
        values = {
            "name": "quota-service",
            "user": self.user,
            "plan": self.plan,
            "network": self.network,
            "source_kind": Service.SourceKind.IMAGE,
            "source_config": {},
        }
        values.update(extra)
        return Service.objects.create(**values)

    def test_storage_quota_is_logical_plan_allocation(self):
        service = self.make_service()
        Volume.objects.create(
            name="data",
            user=self.user,
            service=service,
            size_mb=4096,
            default_bind="/data",
            default_mode="rw",
        )
        summary = service.storage_quota_summary()
        self.assertEqual(summary["quota_mb"], 10 * 1024)
        self.assertEqual(summary["used_mb"], 4096)
        self.assertEqual(summary["quota_mode"], "LOGICAL_ONLY")
        self.assertFalse(summary["physical_enforcement"])

    def test_storage_allocation_rejects_capacity_over_plan(self):
        service = self.make_service()
        ok, message = service.can_allocate_storage(11 * 1024)
        self.assertFalse(ok)
        self.assertIn("Not enough storage", message)

    def test_catalog_managed_source_provenance_is_immutable(self):
        service = self.make_service(
            source_kind=Service.SourceKind.CATALOG,
            source_config={"catalog_id": "wordpress", "variant_id": "mariadb"},
        )
        service.source_config = {"catalog_id": "wordpress", "variant_id": "postgresql"}
        with self.assertRaises(ValidationError):
            service.full_clean()

    def test_transitional_service_cannot_change_plan(self):
        service = self.make_service(status="queued")
        service.plan = self.plan2
        with self.assertRaises(ValidationError):
            service.full_clean()

    def test_service_serializer_blocks_catalog_metadata_changes(self):
        service = self.make_service(
            source_kind=Service.SourceKind.CATALOG,
            source_config={"catalog_id": "uptime-kuma"},
        )
        serializer = ServiceSerializer(
            instance=service,
            data={"plan": str(self.plan2.pk)},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("plan", serializer.errors)

    def test_volume_serializer_rejects_zero_size(self):
        serializer = VolumeSerializer(
            data={
                "name": "invalid",
                "size_mb": 0,
                "default_bind": "/data",
                "default_mode": "rw",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("size_mb", serializer.errors)

    def test_service_orm_changes_invalidate_service_cache(self):
        service = self.make_service(name="cache-hook")
        with patch("core.app_cache.invalidate_user_services") as invalidate:
            service.name = "cache-hook-renamed"
            service.save()
        invalidate.assert_called_with(self.user.id)
