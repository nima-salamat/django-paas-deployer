from __future__ import annotations

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from app_catalog.apis import (
    ApplicationInstanceListCreateAPIView,
    CatalogDetailAPIView,
    CatalogListAPIView,
    CatalogResolveAPIView,
)
from app_catalog.models import ApplicationInstance
from plans.models import Plan
from users.models import User
from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices
from services.models import PrivateNetwork


class ReadyAppPublicApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="ready-app-public-api",
            email="ready-app-public-api@example.invalid",
        )
        common = dict(
            max_cpu=2.0,
            max_ram=4096,
            max_storage=64,
            price_per_hour=1.0,
            storage_type=StorageTypeChoices.SSD,
        )
        cls.app_plan = Plan.objects.create(
            name=NameChoices.BRONZE,
            platform="docker",
            plan_type=PlanTypeChoices.APP,
            **common,
        )
        cls.mariadb_plan = Plan.objects.create(
            name=NameChoices.BRONZE,
            platform="mariadb",
            plan_type=PlanTypeChoices.DB,
            **common,
        )

    def request(self, method, path, data=None):
        request = getattr(APIRequestFactory(), method.lower())(
            path,
            data=data or {},
            format="json",
        )
        force_authenticate(request, user=self.user)
        return request

    def test_catalog_list_contains_only_curated_public_apps(self):
        response = CatalogListAPIView.as_view()(self.request("GET", "/api/application-catalog/apps/"))
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.data}
        self.assertEqual(ids, {"wordpress", "uptime-kuma", "grafana"})
        for row in response.data:
            self.assertNotIn("services", row)
            self.assertNotIn("compose_document", row)

    def test_internal_definition_is_not_discoverable(self):
        response = CatalogDetailAPIView.as_view()(
            self.request("GET", "/api/application-catalog/apps/mattermost/"),
            catalog_id="mattermost",
        )
        self.assertEqual(response.status_code, 404)

    def test_public_detail_hides_runtime_authoring_details_and_domain_field(self):
        response = CatalogDetailAPIView.as_view()(
            self.request("GET", "/api/application-catalog/apps/grafana/"),
            catalog_id="grafana",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], "grafana")
        self.assertTrue(any(field["id"] == "admin_password" for variant in response.data["variants"] for field in variant["fields"]))
        self.assertFalse(any(field["id"] == "domain" for variant in response.data["variants"] for field in variant["fields"]))
        self.assertNotIn("services", response.data)
        self.assertNotIn("environment", response.data)
        self.assertNotIn("image", response.data)

    @override_settings(DEPLOYMENT_DOMAIN="apps.example.test")
    def test_resolve_is_plan_aware_and_returns_resource_and_url_preview_only(self):
        response = CatalogResolveAPIView.as_view()(
            self.request(
                "POST",
                "/api/application-catalog/apps/wordpress/resolve/",
                {
                    "name": "My WordPress",
                    "plan_id": str(self.app_plan.pk),
                    "variant": "default",
                    "config": {},
                },
            ),
            catalog_id="wordpress",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["valid"])
        self.assertEqual(
            response.data["public_endpoints"][0]["url"],
            "https://my-wordpress.apps.example.test",
        )
        self.assertEqual(response.data["resource_summary"]["service_count"], 2)
        self.assertEqual(response.data["resource_summary"]["volume_count"], 2)
        self.assertEqual(response.data["resource_summary"]["storage_mb"], 2048)
        self.assertEqual(response.data["resource_summary"]["cpu_vcpu"], 4.0)
        self.assertEqual(response.data["resource_summary"]["ram_mb"], 8192.0)
        self.assertNotIn("services", response.data)
        self.assertNotIn("secrets", response.data)
        self.assertNotIn("image", str(response.data).lower())

    @override_settings(DEPLOYMENT_DOMAIN="apps.example.test")
    def test_custom_domain_is_rejected_for_managed_hostname_recipe(self):
        response = CatalogResolveAPIView.as_view()(
            self.request(
                "POST",
                "/api/application-catalog/apps/wordpress/resolve/",
                {
                    "name": "wordpress-domain",
                    "plan_id": str(self.app_plan.pk),
                    "variant": "default",
                    "config": {"domain": "evil.example.test"},
                },
            ),
            catalog_id="wordpress",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("managed automatically", response.data["error"])

    def test_non_public_installation_is_rejected_at_api_boundary(self):
        response = ApplicationInstanceListCreateAPIView.as_view()(
            self.request(
                "POST",
                "/api/application-catalog/installations/",
                {
                    "catalog_id": "mattermost",
                    "variant": "postgresql",
                    "name": "internal-mattermost",
                    "plan_id": str(self.app_plan.pk),
                    "config": {"domain": "internal-mattermost.example.test", "storage_mb": 4096},
                },
            )
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not available", response.data["error"])

    @override_settings(DEPLOYMENT_DOMAIN="apps.example.test")
    def test_duplicate_installation_conflict_returns_existing_id(self):
        network = PrivateNetwork.objects.create(
            user=self.user,
            name="existing-ready-app-network",
        )
        existing = ApplicationInstance.objects.create(
            user=self.user,
            name="existing-ready-app",
            slug="existing-ready-app",
            catalog_id="wordpress",
            definition_version="1.0",
            software_version="7.1.2",
            variant_id="default",
            definition_snapshot={},
            config={},
            network=network,
        )
        response = ApplicationInstanceListCreateAPIView.as_view()(
            self.request(
                "POST",
                "/api/application-catalog/installations/",
                {
                    "catalog_id": "wordpress",
                    "variant": "default",
                    "name": "existing-ready-app",
                    "plan_id": str(self.app_plan.pk),
                    "config": {},
                },
            )
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "application_name_conflict")
        self.assertEqual(response.data["existing_installation_id"], str(existing.pk))
