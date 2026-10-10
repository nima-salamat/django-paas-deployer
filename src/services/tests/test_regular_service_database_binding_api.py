from rest_framework.test import APIRequestFactory, force_authenticate
from django.test import TestCase

from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices
from deploy.models import Deploy
from plans.models import Plan
from services.api.configuration import (
    DatabaseResourceAPIView,
    ServiceDatabaseBindingsAPIView,
)
from services.models import (
    DatabaseCredential,
    DatabaseResource,
    PrivateNetwork,
    Service,
    ServiceDatabaseBinding,
    ServiceSecret,
)
from services.revisioning import _database_environment_snapshot
from users.models import User


class RegularServiceDatabaseBindingApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="regular-db-binding",
            email="regular-db-binding@example.invalid",
        )
        common = {
            "max_cpu": 1,
            "max_ram": 1024,
            "max_storage": 10,
            "price_per_hour": 0,
            "storage_type": StorageTypeChoices.SSD,
        }
        cls.workload_plan = Plan.objects.create(
            name=NameChoices.BRONZE,
            platform="docker",
            plan_type=PlanTypeChoices.APP,
            **common,
        )
        cls.database_plan = Plan.objects.create(
            name=NameChoices.BRONZE,
            platform="postgresql",
            plan_type=PlanTypeChoices.DB,
            **common,
        )
        cls.network = PrivateNetwork.objects.create(
            name="regular-db-network",
            user=cls.user,
            description="Test database connectivity boundary",
        )

    def _service(self, name, plan, *, network=None, user=None):
        return Service.objects.create(
            name=name,
            user=user or self.user,
            plan=plan,
            network=network,
        )

    def _request(self, method, path, *, data=None, user=None):
        factory = APIRequestFactory()
        if method == "get":
            request = factory.get(path)
        elif method == "post":
            request = factory.post(path, data or {}, format="json")
        else:
            raise AssertionError(f"Unsupported test method: {method}")
        force_authenticate(request, user=user or self.user)
        return request

    def _provider_with_credentials(self, name="regular-postgres"):
        provider = self._service(name, self.database_plan, network=self.network)
        deploy = Deploy.objects.create(
            name=f"{name}-deploy",
            service=provider,
            created_by=self.user,
            version=1.0,
            config={
                "database": "application_db",
                "username": "application_user",
                "password": "db-password-not-for-api",
            },
        )
        provider.selected_deploy = deploy
        provider.save(update_fields=["selected_deploy", "updated_at"])
        return provider

    def test_resource_list_includes_existing_db_services_without_exposing_credentials(self):
        workload = self._service("regular-workload", self.workload_plan, network=self.network)
        provider = self._provider_with_credentials()

        request = self._request(
            "get",
            f"/services/service/{workload.pk}/database-resources/",
        )
        response = DatabaseResourceAPIView.as_view()(request, service_id=workload.pk)

        self.assertEqual(response.status_code, 200)
        results = response.data["results"]
        candidate = next(item for item in results if item["id"] == f"service:{provider.pk}")
        self.assertEqual(candidate["resource_type"], "database_service")
        self.assertEqual(candidate["engine"], "postgresql")
        self.assertEqual(candidate["host"], provider.get_docker_service_name())
        self.assertEqual(candidate["port"], 5432)
        self.assertTrue(candidate["connectable"])
        self.assertNotIn("password", candidate)
        self.assertNotIn("username", candidate)

    def test_binding_existing_db_service_stores_credentials_and_materializes_runtime_secrets(self):
        workload = self._service("regular-workload-binding", self.workload_plan, network=self.network)
        provider = self._provider_with_credentials("regular-postgres-binding")

        request = self._request(
            "post",
            f"/services/service/{workload.pk}/databases/",
            data={
                "database": f"service:{provider.pk}",
                "alias": "primary",
                "env_prefix": "APP_DB",
                "access_mode": "rw",
            },
        )
        response = ServiceDatabaseBindingsAPIView.as_view()(request, service_id=workload.pk)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["binding_status"], "configured_unverified")
        self.assertEqual(response.data["engine"], "postgresql")
        self.assertEqual(response.data["host"], provider.get_docker_service_name())
        self.assertEqual(response.data["port"], 5432)
        self.assertNotIn("password", response.data)
        self.assertNotIn("username", response.data)

        resource = DatabaseResource.objects.get(provider_service=provider)
        self.assertEqual(resource.database_name, "application_db")
        credential = DatabaseCredential.objects.get(database=resource)
        self.assertEqual(credential.username, "application_user")
        self.assertEqual(credential.get_password(), "db-password-not-for-api")
        binding = ServiceDatabaseBinding.objects.get(service=workload, alias="primary")
        self.assertEqual(binding.database, resource)
        self.assertEqual(binding.env_prefix, "APP_DB")

        env, secret_refs = _database_environment_snapshot(workload, created_by=self.user)
        self.assertEqual(env["APP_DB_HOST"], provider.get_docker_service_name())
        self.assertEqual(env["APP_DB_PORT"], "5432")
        self.assertEqual(env["APP_DB_NAME"], "application_db")
        self.assertEqual(env["APP_DB_DATABASE"], "application_db")
        self.assertEqual(env["APP_DB_ENGINE"], "postgresql")
        self.assertEqual(env["APP_DB_USER"], "application_user")
        self.assertNotIn("APP_DB_PASSWORD", env)
        self.assertTrue(any(ref.get("path") == "env.APP_DB_PASSWORD" for ref in secret_refs))
        stored_secret = ServiceSecret.objects.get(service=workload, key="APP_DB_PASSWORD")
        self.assertEqual(stored_secret.get_current_value(), "db-password-not-for-api")

    def test_binding_rejects_database_service_on_a_different_private_network(self):
        workload = self._service("regular-workload-network", self.workload_plan, network=self.network)
        other_network = PrivateNetwork.objects.create(
            name="different-db-network",
            user=self.user,
            description="Must not be reachable by the workload",
        )
        provider = self._service("isolated-postgres", self.database_plan, network=other_network)

        request = self._request(
            "post",
            f"/services/service/{workload.pk}/databases/",
            data={"database": f"service:{provider.pk}", "env_prefix": "DB"},
        )
        response = ServiceDatabaseBindingsAPIView.as_view()(request, service_id=workload.pk)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "database_network_mismatch")
        self.assertFalse(ServiceDatabaseBinding.objects.filter(service=workload).exists())
        self.assertFalse(DatabaseResource.objects.filter(provider_service=provider).exists())

    def test_duplicate_environment_prefix_is_rejected_before_creating_provider_resource(self):
        workload = self._service("regular-workload-prefix", self.workload_plan, network=self.network)
        first_provider = self._provider_with_credentials("regular-postgres-first")
        first_resource = DatabaseResource.objects.create(
            owner=self.user,
            provider_service=first_provider,
            name="registered-first-db",
            engine="postgresql",
            host=first_provider.get_docker_service_name(),
            port=5432,
            database_name="application_db",
            status="provisioned",
        )
        ServiceDatabaseBinding.objects.create(
            service=workload,
            database=first_resource,
            alias="first",
            env_prefix="APP_DB",
            access_mode="rw",
        )
        second_provider = self._provider_with_credentials("regular-postgres-second")

        request = self._request(
            "post",
            f"/services/service/{workload.pk}/databases/",
            data={
                "database": f"service:{second_provider.pk}",
                "alias": "second",
                "env_prefix": "APP_DB",
                "access_mode": "rw",
            },
        )
        response = ServiceDatabaseBindingsAPIView.as_view()(request, service_id=workload.pk)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "database_env_prefix_conflict")
        self.assertFalse(DatabaseResource.objects.filter(provider_service=second_provider).exists())
