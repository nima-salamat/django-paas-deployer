from __future__ import annotations

import threading

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from app_catalog.apis import (
    ApplicationInstanceListCreateAPIView,
    CatalogDetailAPIView,
    CatalogListAPIView,
    CatalogResolveAPIView,
    ApplicationInstanceDetailAPIView,
)
from app_catalog.models import ApplicationInstance, ApplicationStatus, CatalogPublication
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

    def test_operator_publication_override_can_hide_curated_app(self):
        CatalogPublication.objects.create(
            catalog_id="wordpress",
            enabled=False,
        )
        response = CatalogListAPIView.as_view()(
            self.request("GET", "/api/application-catalog/apps/")
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("wordpress", {row["id"] for row in response.data})

    def test_operator_publication_override_can_control_featured_flag(self):
        CatalogPublication.objects.create(
            catalog_id="wordpress",
            enabled=True,
            featured_override=False,
        )
        response = CatalogDetailAPIView.as_view()(
            self.request("GET", "/api/application-catalog/apps/wordpress/"),
            catalog_id="wordpress",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["featured"])

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
        self.assertEqual(
            (wordpress.source_config or {}).get("application_instance"),
            str(instance.pk),
        )
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

    def test_repeated_delete_request_does_not_refresh_deletion_intent(self):
        from unittest.mock import patch
        from app_catalog.services import create_application_installation

        instance = create_application_installation(
            self.user,
            {
                "catalog_id": "wordpress",
                "variant": "default",
                "name": "delete-intent-idempotent",
                "plan_id": str(self.app_plan.pk),
                "config": {},
            },
            require_public=True,
        )

        with (
            patch("app_catalog.executor.ApplicationStackExecutor.cleanup_terminal_application", return_value=False),
            patch("app_catalog.apis.delete_application_installation.delay") as queue,
        ):
            first = ApplicationInstanceDetailAPIView.as_view()(
                self.request("DELETE", f"/api/application-catalog/installations/{instance.pk}/"),
                pk=instance.pk,
            )
            updated_at_after_first = ApplicationInstance.objects.get(pk=instance.pk).updated_at
            second = ApplicationInstanceDetailAPIView.as_view()(
                self.request("DELETE", f"/api/application-catalog/installations/{instance.pk}/"),
                pk=instance.pk,
            )
            updated_at_after_second = ApplicationInstance.objects.get(pk=instance.pk).updated_at

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(queue.call_count, 1)
        self.assertEqual(updated_at_after_first, updated_at_after_second)


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

        with patch(
            "app_catalog.executor.ApplicationStackExecutor.cleanup_terminal_application",
            return_value=False,
        ) as cleanup:
            response = ApplicationInstanceDetailAPIView.as_view()(
                self.request("DELETE", f"/api/application-catalog/installations/{instance.pk}/"),
                pk=instance.pk,
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["code"], "application_cleanup_pending")
        cleanup.assert_called_once_with()
        binding.deploy.refresh_from_db()
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

        with patch(
            "app_catalog.executor.ApplicationStackExecutor.cleanup_terminal_application",
            return_value=True,
        ) as cleanup:
            response = ApplicationInstanceDetailAPIView.as_view()(
                self.request("DELETE", f"/api/application-catalog/installations/{instance.pk}/"),
                pk=instance.pk,
            )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(ApplicationInstance.objects.filter(pk=instance.pk).exists())
        self.assertTrue(ApplicationInstance.objects.filter(pk=instance.pk).count() == 0)
        cleanup.assert_called_once_with()

    def test_failed_delete_recovers_legacy_orphan_service_before_private_network(self):
        from unittest.mock import patch
        from deploy.models import DeploymentStatusChoices
        from app_catalog.services import create_application_installation

        instance = create_application_installation(
            self.user,
            {
                "catalog_id": "wordpress",
                "variant": "default",
                "name": "legacy-orphan-delete",
                "plan_id": str(self.app_plan.pk),
                "config": {},
            },
            require_public=True,
        )
        instance.status = ApplicationStatus.FAILED
        instance.save(update_fields=["status", "updated_at"])

        orphan = instance.services.get(service_key="mariadb")
        orphan_service = orphan.service

        orphan.delete()
        orphan_service.source_config = {
            key: value
            for key, value in dict(orphan_service.source_config or {}).items()
            if key != "application_instance"
        }
        orphan_service.save(update_fields=["source_config", "updated_at"])

        network_id = instance.network_id
        self.assertFalse(
            instance.services.filter(service_id=orphan_service.pk).exists()
        )
        self.assertTrue(
            __import__("services.models", fromlist=["Service"]).Service.objects.filter(
                pk=orphan_service.pk,
                network_id=network_id,
            ).exists()
        )

        with (
            patch("services.signals.cleanup_service_resources"),
            patch("services.signals._cleanup_service_log_records"),
            patch("services.signals.Network.network_exists", return_value=False),
        ):
            response = ApplicationInstanceDetailAPIView.as_view()(
                self.request("DELETE", f"/api/application-catalog/installations/{instance.pk}/"),
                pk=instance.pk,
            )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            ApplicationInstance.objects.filter(pk=instance.pk).exists()
        )
        self.assertFalse(
            __import__("services.models", fromlist=["Service"]).Service.objects.filter(
                pk=orphan_service.pk,
            ).exists()
        )
        self.assertFalse(
            PrivateNetwork.objects.filter(pk=network_id).exists()
        )


    def test_running_delete_cancels_active_children_and_queues_cleanup(self):
        from unittest.mock import patch
        from deploy.models import DeploymentStatusChoices
        from app_catalog.services import create_application_installation
        from app_catalog.tasks import delete_application_installation

        instance = create_application_installation(
            self.user,
            {
                "catalog_id": "wordpress",
                "variant": "default",
                "name": "running-delete-queue",
                "plan_id": str(self.app_plan.pk),
                "config": {},
            },
            require_public=True,
        )
        instance.status = ApplicationStatus.RUNNING
        instance.save(update_fields=["status", "updated_at"])

        binding = instance.services.select_related("service", "deploy").first()
        binding.deploy.status = DeploymentStatusChoices.RUNNING
        binding.deploy.save(update_fields=["status", "updated_at"])

        with (
            patch(
                "app_catalog.executor.ApplicationStackExecutor.cleanup_terminal_application",
                return_value=False,
            ) as cleanup,
            patch.object(delete_application_installation, "delay") as queued,
        ):
            response = ApplicationInstanceDetailAPIView.as_view()(
                self.request("DELETE", f"/api/application-catalog/installations/{instance.pk}/"),
                pk=instance.pk,
            )

        self.assertEqual(response.status_code, 202)
        instance.refresh_from_db()
        self.assertEqual(instance.stage, "deletion_pending")
        cleanup.assert_called_once_with()
        queued.assert_called_once_with(str(instance.pk))
        self.assertTrue(instance.cancel_requested)
        self.assertTrue(ApplicationInstance.objects.filter(pk=instance.pk).exists())

    def test_deploying_delete_is_accepted_and_marked_for_coordinator_cleanup(self):
        from unittest.mock import patch
        from app_catalog.services import create_application_installation
        from app_catalog.tasks import delete_application_installation

        instance = create_application_installation(
            self.user,
            {
                "catalog_id": "wordpress",
                "variant": "default",
                "name": "deploying-delete",
                "plan_id": str(self.app_plan.pk),
                "config": {},
            },
            require_public=True,
        )
        instance.status = ApplicationStatus.DEPLOYING
        instance.save(update_fields=["status", "updated_at"])

        with (
            patch(
                "app_catalog.executor.ApplicationStackExecutor.cleanup_terminal_application",
                return_value=False,
            ),
            patch.object(delete_application_installation, "delay") as queued,
        ):
            response = ApplicationInstanceDetailAPIView.as_view()(
                self.request("DELETE", f"/api/application-catalog/installations/{instance.pk}/"),
                pk=instance.pk,
            )

        self.assertEqual(response.status_code, 202)
        instance.refresh_from_db()
        self.assertEqual(instance.stage, "deletion_pending")
        self.assertTrue(instance.cancel_requested)
        queued.assert_called_once_with(str(instance.pk))

    def test_failed_delete_queues_durable_cleanup_after_resource_failure(self):
        from unittest.mock import patch
        from app_catalog.services import create_application_installation
        from app_catalog.tasks import delete_application_installation

        instance = create_application_installation(
            self.user,
            {
                "catalog_id": "wordpress",
                "variant": "default",
                "name": "failed-delete-queued",
                "plan_id": str(self.app_plan.pk),
                "config": {},
            },
            require_public=True,
        )
        instance.status = ApplicationStatus.FAILED
        instance.error_code = "APPLICATION_SERVICE_DEPLOYMENT_FAILED"
        instance.error_message = "mariadb: database deployment failed"
        instance.save(update_fields=["status", "error_code", "error_message", "updated_at"])

        with (
            patch("services.signals.cleanup_service_resources", side_effect=RuntimeError("volume is still in use")),
            patch.object(delete_application_installation, "delay") as queued,
        ):
            response = ApplicationInstanceDetailAPIView.as_view()(
                self.request("DELETE", f"/api/application-catalog/installations/{instance.pk}/"),
                pk=instance.pk,
            )

        self.assertEqual(response.status_code, 202)
        instance.refresh_from_db()
        self.assertEqual(instance.stage, "deletion_pending")
        self.assertEqual(instance.error_code, "APPLICATION_DELETION_PENDING")
        queued.assert_called_once_with(str(instance.pk))
        self.assertTrue(ApplicationInstance.objects.filter(pk=instance.pk).exists())

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


class ReadyAppDeletionConcurrencyTests(TransactionTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="ready-app-delete-race",
            email="ready-app-delete-race@example.invalid",
        )

    def test_concurrent_delete_requests_enqueue_only_one_durable_task(self):
        from unittest.mock import patch
        from app_catalog.apis import _queue_ready_app_deletion

        if connection.vendor != "postgresql":
            self.skipTest("Deletion intent race requires PostgreSQL row locking.")

        instance = ApplicationInstance.objects.create(
            user=self.user,
            name="delete-race",
            slug="delete-race",
            catalog_id="wordpress",
            definition_version="1.0",
            software_version="7.1.2",
            variant_id="default",
            definition_snapshot={"_application_orchestration": {"services": []}},
            status=ApplicationStatus.FAILED,
        )

        barrier = threading.Barrier(2)
        errors = []

        def cleanup():
            barrier.wait(timeout=10)
            return False

        def worker():
            close_old_connections()
            try:
                _queue_ready_app_deletion(str(instance.pk))
            except Exception as exc:
                errors.append(exc)
            finally:
                close_old_connections()

        with (
            patch("app_catalog.executor.ApplicationStackExecutor.cleanup_terminal_application", side_effect=cleanup),
            patch("app_catalog.apis.delete_application_installation.delay") as queued,
        ):
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)

        assert not errors
        assert queued.call_count == 1
        instance.refresh_from_db()
        assert instance.stage == "deletion_pending"
        assert instance.error_code == "APPLICATION_DELETION_PENDING"

