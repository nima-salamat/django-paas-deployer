from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from users.models import Rule

from plans.models import Plan
from plans.serializers import PlanSerializer, UnauthorizedPlanSerializer

User = get_user_model()


class PlanModelAndSerializerTests(TestCase):
    def make_plan(self, **overrides):
        values = {
            "name": "Bronze",
            "platform": "python",
            "plan_type": "APP",
            "max_cpu": 1.5,
            "max_ram": 1024,
            "max_storage": 20,
            "price_per_hour": 2500,
            "storage_type": "SSD",
            "log_retention_days": 7,
            "log_storage_mb": 512,
            "log_ingest_bytes_per_sec": 8192,
            "persistent_logging": True,
            "realtime_logging": True,
            "log_quota_behavior": "fifo_delete",
        }
        values.update(overrides)
        return Plan.objects.create(**values)

    def test_plan_pricing_helpers_are_consistent(self):
        plan = self.make_plan(price_per_hour=1250.5)
        self.assertEqual(plan.price_per_day, 30012.0)
        self.assertEqual(plan.price_per_month, 900360.0)

    def test_plan_serializer_round_trips_all_policy_fields(self):
        plan = self.make_plan()
        data = PlanSerializer(plan).data
        for field in (
            "name",
            "platform",
            "plan_type",
            "max_cpu",
            "max_ram",
            "max_storage",
            "price_per_hour",
            "storage_type",
            "log_retention_days",
            "log_storage_mb",
            "log_ingest_bytes_per_sec",
            "persistent_logging",
            "realtime_logging",
            "log_quota_behavior",
        ):
            self.assertIn(field, data)

        self.assertFalse(PlanSerializer().fields["id"].write_only)

    def test_unauthorized_serializer_never_uses_placeholder_duplicate_price_fields(self):
        fields = list(UnauthorizedPlanSerializer().fields)
        self.assertEqual(fields.count("price_per_hour"), 1)
        self.assertIn("price_per_day", fields)
        self.assertIn("price_per_month", fields)


class PlanPermissionAndAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.plan = Plan.objects.create(
            name="Bronze",
            platform="python",
            plan_type="APP",
            max_cpu=1,
            max_ram=512,
            max_storage=10,
            price_per_hour=100,
            storage_type="HDD",
        )
        self.viewer = User.objects.create_user(
            username="plan-viewer",
            password="password123",
            is_staff=True,
        )
        self.manager = User.objects.create_user(
            username="plan-manager",
            password="password123",
            is_staff=True,
        )
        self.outsider = User.objects.create_user(
            username="plan-outsider",
            password="password123",
            is_staff=True,
        )
        Rule.objects.create(user=self.viewer, rules=["plans.view"])
        Rule.objects.create(user=self.manager, rules=["plans.manage"])

    def test_public_plan_list_is_available_without_authentication(self):
        response = self.client.get("/plans/")
        self.assertEqual(response.status_code, 200)

    def test_plan_admin_viewer_can_read_but_cannot_mutate(self):
        self.client.force_authenticate(user=self.viewer)

        read = self.client.get("/plans/admin/plans/")
        create = self.client.post(
            "/plans/admin/plans/",
            {
                "name": "Silver",
                "platform": "python",
                "plan_type": "APP",
                "max_cpu": 2,
                "max_ram": 2048,
                "max_storage": 40,
                "price_per_hour": 200,
                "storage_type": "SSD",
            },
            format="json",
        )

        self.assertEqual(read.status_code, 200)
        self.assertEqual(create.status_code, 403)

    def test_plan_admin_manager_can_create_update_and_delete_unused_plan(self):
        self.client.force_authenticate(user=self.manager)

        created = self.client.post(
            "/plans/admin/plans/",
            {
                "name": "Silver",
                "platform": "python",
                "plan_type": "APP",
                "max_cpu": 2,
                "max_ram": 2048,
                "max_storage": 40,
                "price_per_hour": 200,
                "storage_type": "SSD",
                "log_retention_days": 14,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        plan_id = created.json()["data"]["id"]

        updated = self.client.patch(
            f"/plans/admin/plans/{plan_id}/",
            {"max_cpu": 4, "log_retention_days": 30},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(
            Plan.objects.get(pk=plan_id).max_cpu,
            4,
        )

        deleted = self.client.delete(f"/plans/admin/plans/{plan_id}/")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(Plan.objects.filter(pk=plan_id).exists())

    def test_nonstaff_staff_without_rules_and_invalid_uuid_are_denied_or_rejected(self):
        self.client.force_authenticate(user=self.outsider)
        self.assertEqual(self.client.get("/plans/admin/plans/").status_code, 403)

        self.client.force_authenticate(user=self.manager)
        self.assertEqual(
            self.client.get("/plans/admin/plans/not-a-uuid/").status_code,
            404,
        )

    def test_admin_list_uses_cached_payload_when_available(self):
        self.client.force_authenticate(user=self.viewer)
        cached = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [{"id": str(self.plan.pk)}],
        }
        with patch("core.app_cache.cache_get", return_value=cached) as cache_get:
            response = self.client.get("/plans/admin/plans/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), cached)
        cache_get.assert_called_once()

    def test_plan_write_invalidates_plan_cache(self):
        self.client.force_authenticate(user=self.manager)
        with patch("core.app_cache.invalidate_all_plans") as invalidate:
            response = self.client.post(
                "/plans/admin/plans/",
                {
                    "name": "Gold",
                    "platform": "docker",
                    "plan_type": "READY",
                    "max_cpu": 1,
                    "max_ram": 1024,
                    "max_storage": 10,
                    "price_per_hour": 10,
                    "storage_type": "HDD",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        invalidate.assert_called()
