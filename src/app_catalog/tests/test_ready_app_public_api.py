from __future__ import annotations

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from app_catalog.apis import (
    ApplicationInstanceListCreateAPIView,
    CatalogDetailAPIView,
    CatalogListAPIView,
    CatalogResolveAPIView,
    ApplicationInstanceDetailAPIView,
)
from app_catalog.models import ApplicationInstance, ApplicationStatus
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
    def test_resolve_is_plan_aware_without_exposing_pre_deployment_hostname(self):
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
        self.assertEqual(response.data["resource_summary"]["service_count"], 2)
        self.assertEqual(response.data["resource_summary"]["volume_count"], 2)
        self.assertEqual(response.data["resource_summary"]["storage_mb"], 2048)
        self.assertEqual(response.data["resource_summary"]["cpu_vcpu"], 4.0)
        self.assertEqual(response.data["resource_summary"]["ram_mb"], 8192.0)
        self.assertNotIn("services", response.data)
        self.assertNotIn("secrets", response.data)
        self.assertNotIn("public_endpoints", response.data)
        self.assertNotIn("my-wordpress.apps.example.test", str(response.data))
        self.assertNotIn("apps.example.test", str(response.data))
        self.assertNotIn("image", str(response.data).lower())

    @override_settings(DEPLOYMENT_DOMAIN="apps.example.test")
    def test_ready_app_public_hostname_uses_created_service_id(self):
        from app_catalog.services import create_application_installation

        instance = create_application_installation(
            self.user,
            {
                "catalog_id": "wordpress",
                "variant": "default",
                "name": "friendly-wordpress-name",
                "plan_id": str(self.app_plan.pk),
                "config": {},
            },
            require_public=True,
        )
        wordpress = instance.services.get(service_key="wordpress").service
        endpoint = wordpress.endpoints.get(exposure="public")

        expected = (
            f"{wordpress.get_docker_service_name()}.apps.example.test"
        )
        self.assertEqual(endpoint.hostname, expected)
        self.assertNotEqual(endpoint.hostname, "friendly-wordpress-name.apps.example.test")

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

    def test_cancelled_delete_requests_remaining_child_cleanup_instead_of_blocking(self):
        from deploy.models import DeploymentStatusChoices
        from app_catalog.services import create_application_installation

        instance = create_application_installation(
            self.user,
            {
                "catalog_id": "wordpress",
                "variant": "default",
                "name": "cancel-delete-pending",
                "plan_id": str(self.app_plan.pk),
                "config": {},
            },
            require_public=True,
        )
        instance.status = ApplicationStatus.CANCELLED
        instance.cancel_requested = True
        instance.save(update_fields=["status", "cancel_requested", "updated_at"])

        binding = instance.services.select_related("deploy").first()
        binding.deploy.status = DeploymentStatusChoices.RUNNING
        binding.deploy.save(update_fields=["status", "updated_at"])

        response = ApplicationInstanceDetailAPIView.as_view()(
            self.request("DELETE", f"/api/application-catalog/installations/{instance.pk}/"),
            pk=instance.pk,
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["code"], "application_cleanup_pending")
        binding.deploy.refresh_from_db()
        self.assertTrue(binding.deploy.cancel_requested)
        self.assertTrue(ApplicationInstance.objects.filter(pk=instance.pk).exists())

    def test_cancelled_delete_finishes_after_child_deploys_are_terminal(self):
        from unittest.mock import patch
        from deploy.models import DeploymentStatusChoices
        from app_catalog.services import create_application_installation

        instance = create_application_installation(
            self.user,
            {
                "catalog_id": "wordpress",
                "variant": "default",
                "name": "cancel-delete-finish",
                "plan_id": str(self.app_plan.pk),
                "config": {},
            },
            require_public=True,
        )
        instance.status = ApplicationStatus.CANCELLED
        instance.cancel_requested = True
        instance.save(update_fields=["status", "cancel_requested", "updated_at"])

        bindings = list(instance.services.select_related("service", "deploy"))
        for binding in bindings:
            binding.deploy.status = DeploymentStatusChoices.CANCELLED
            binding.deploy.save(update_fields=["status", "updated_at"])

        network = instance.network
        with patch("services.models.Service.delete") as service_delete, patch.object(network, "delete") as network_delete:
            response = ApplicationInstanceDetailAPIView.as_view()(
                self.request("DELETE", f"/api/application-catalog/installations/{instance.pk}/"),
                pk=instance.pk,
            )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(ApplicationInstance.objects.filter(pk=instance.pk).exists())
        self.assertEqual(service_delete.call_count, len(bindings))
        network_delete.assert_called()

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
