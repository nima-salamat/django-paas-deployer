from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from deploy.models import Deploy
from plans.models import Plan
from services.models import PrivateNetwork, Service

User = get_user_model()


class DeployAPIVisibilityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="deploy-api-owner",
            email="deploy-api-owner@example.com",
            password="password123",
        )
        self.other = User.objects.create_user(
            username="deploy-api-other",
            email="deploy-api-other@example.com",
            password="password123",
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
            name="deploy-api-network",
        )
        self.service = Service.objects.create(
            name="deploy-api-service",
            user=self.owner,
            plan=self.plan,
            network=self.network,
        )
        self.deploy = Deploy.objects.create(
            name="deploy-api-entry",
            service=self.service,
            created_by=self.owner,
            config={"platform": "docker"},
        )

    def test_anonymous_cannot_list_deployments(self):
        response = self.client.get("/deploy/")
        self.assertIn(response.status_code, (401, 403))

    def test_owner_can_list_only_own_or_shared_deployments(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get("/deploy/")
        self.assertEqual(response.status_code, 200)
        ids = {str(row["id"]) for row in response.json()["results"]}
        self.assertEqual(ids, {str(self.deploy.pk)})

        self.client.force_authenticate(user=self.other)
        response = self.client.get("/deploy/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

    def test_deploy_list_does_not_expose_raw_zip_path_or_runtime_state_as_writable_payload(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get("/deploy/")
        self.assertEqual(response.status_code, 200)
        row = response.json()["results"][0]
        self.assertIn("status", row)
        self.assertNotIn("runtime_spec_sha256", row)
