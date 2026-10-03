from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from plans.models import Plan
from services.models import PrivateNetwork, Service, Volume
from users.models import Rule

User = get_user_model()


class ServiceAdminAPIPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="svc-admin-owner",
            email="svc-owner@example.com",
            password="password123",
        )
        self.staff = User.objects.create_user(
            username="svc-admin-staff",
            email="svc-staff@example.com",
            password="password123",
            is_staff=True,
        )
        self.plan = Plan.objects.create(
            name="Bronze",
            platform="docker",
            plan_type="APP",
            max_cpu=1,
            max_ram=512,
            max_storage=10,
            price_per_hour=1,
            storage_type="SSD",
        )
        self.network = PrivateNetwork.objects.create(
            user=self.owner,
            name="svc-admin-network",
        )
        self.service = Service.objects.create(
            name="svc-admin-service",
            user=self.owner,
            plan=self.plan,
            network=self.network,
        )
        self.volume = Volume.objects.create(
            name="svc-admin-volume",
            user=self.owner,
            service=self.service,
            size_mb=256,
            default_bind="/data",
            default_mode="rw",
        )

    def test_staff_without_service_rule_cannot_access_admin_services(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get("/services/admin/services/")
        self.assertEqual(response.status_code, 403)

    def test_services_view_can_read_but_not_mutate(self):
        Rule.objects.create(user=self.staff, rules=["services.view"])
        self.client.force_authenticate(user=self.staff)

        read = self.client.get("/services/admin/services/")
        self.assertEqual(read.status_code, 200)

        denied = self.client.post(
            "/services/admin/services/",
            {
                "user_id": self.owner.id,
                "name": "should-not-create",
                "plan": str(self.plan.pk),
            },
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

    def test_services_manage_can_list_and_create_network_for_target_user(self):
        Rule.objects.create(user=self.staff, rules=["services.manage"])
        self.client.force_authenticate(user=self.staff)

        response = self.client.post(
            "/services/admin/networks/",
            {
                "user_id": self.owner.id,
                "name": "admin-created-network",
                "description": "created by staff",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            PrivateNetwork.objects.filter(
                user=self.owner,
                name="admin-created-network",
            ).exists()
        )

    def test_service_admin_list_cache_is_used(self):
        Rule.objects.create(user=self.staff, rules=["services.view"])
        self.client.force_authenticate(user=self.staff)

        from unittest.mock import patch

        cached = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [{"id": str(self.service.pk)}],
        }
        with patch("core.app_cache.cache_get", return_value=cached) as cache_get:
            response = self.client.get("/services/admin/services/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), cached)
        cache_get.assert_called_once()
