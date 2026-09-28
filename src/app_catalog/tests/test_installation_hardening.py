from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from unittest.mock import patch

from app_catalog.executor import ApplicationStackExecutor
from app_catalog.catalog import CatalogDefinition, CatalogValidationError
from app_catalog.models import ApplicationInstance
from app_catalog.services import create_application_installation
from plans.models import Plan
from services.models import ServiceEnvironmentVariable
from users.models import User
from core.global_settings.config import PlanTypeChoices, StorageTypeChoices


class ApplicationInstallationHardeningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="catalog-hardening",
            email="catalog-hardening@example.invalid",
        )
        cls.plan = Plan.objects.create(
            name="Bronze",
            platform="docker",
            plan_type=PlanTypeChoices.APP,
            max_cpu=2.0,
            max_ram=4096,
            max_storage=20,
            price_per_hour=0,
            storage_type=StorageTypeChoices.SSD,
        )

    def _install(self, catalog_id="n8n-with-postgres-and-worker", variant="default", name="catalog-hardening"):
        return create_application_installation(
            self.user,
            {
                "catalog_id": catalog_id,
                "variant": variant,
                "name": name,
                "plan_id": self.plan.pk,
                "config": {"domain": f"{name}.example.invalid"},
            },
        )

    def test_recovery_does_not_regenerate_catalog_secrets(self):
        instance = self._install()
        bindings = list(instance.services.select_related("service"))
        secret_values = {
            (binding.service_key, secret.key): secret.get_current_value()
            for binding in bindings
            for secret in binding.service.secrets.all()
        }
        self.assertTrue(secret_values)

        executor = ApplicationStackExecutor(str(instance.pk))
        _, first_plan = executor._load()
        _, second_plan = executor._load()

        self.assertEqual(first_plan, second_plan)

        with patch("app_catalog.catalog.ApplicationCatalog.get", side_effect=AssertionError("catalog re-read")):
            _, recovered_plan = executor._load()
        self.assertEqual(first_plan, recovered_plan)

        for binding in ApplicationInstance.objects.get(pk=instance.pk).services.select_related("service"):
            for secret in binding.service.secrets.all():
                self.assertEqual(
                    secret_values[(binding.service_key, secret.key)],
                    secret.get_current_value(),
                )

    def test_installation_rolls_back_all_database_children_on_materialization_failure(self):
        from services.models import PrivateNetwork, Service

        before_networks = PrivateNetwork.objects.count()
        before_services = Service.objects.count()
        before_instances = ApplicationInstance.objects.count()

        with patch(
            "app_catalog.services.Service.objects.create",
            side_effect=RuntimeError("injected service creation failure"),
        ):
            with self.assertRaises(RuntimeError):
                self._install(name="catalog-rollback")

        self.assertEqual(PrivateNetwork.objects.count(), before_networks)
        self.assertEqual(Service.objects.count(), before_services)
        self.assertEqual(ApplicationInstance.objects.count(), before_instances)

    def test_installation_snapshot_contains_immutable_orchestration_graph(self):
        instance = self._install(name="catalog-snapshot")
        graph = (instance.definition_snapshot or {}).get("_application_orchestration")
        self.assertIsInstance(graph, dict)
        self.assertEqual(
            {item["key"] for item in graph["services"]},
            {binding.service_key for binding in instance.services.all()},
        )


    def test_concurrent_name_integrity_error_is_exposed_as_conflict(self):
        from app_catalog.apis import ApplicationInstanceListCreateAPIView
        from app_catalog.services import ApplicationNameConflict

        request = APIRequestFactory().post(
            "/installations/",
            {
                "catalog_id": "n8n-with-postgres-and-worker",
                "variant": "default",
                "name": "catalog-race",
                "plan_id": self.plan.pk,
                "config": {"domain": "catalog-race.example.invalid"},
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        with patch(
            "app_catalog.apis.create_application_installation",
            side_effect=ApplicationNameConflict("An application with this name already exists."),
        ):
            response = ApplicationInstanceListCreateAPIView.as_view()(request)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "application_name_conflict")


    def _fake_catalog_materialization(self, *, dockerfile=None, environment=None):
        definition = CatalogDefinition(
            data={
                "id": "hardening-fixture",
                "name": "Hardening Fixture",
                "version": "1",
                "description": "test",
                "category": "test",
                "variants": {"default": {}},
            },
            source=__import__("pathlib").Path("<test>"),
        )
        resolved = {
            "catalog_id": "hardening-fixture",
            "definition_version": "1",
            "software_version": "1",
            "variant_id": "default",
            "config": {},
            "secrets": {"token": "fixed-secret"},
            "services": [{
                "key": "web",
                "role": "app",
                "platform": "docker",
                "plan_type": "APP",
                "image": "example/web:1",
                "dockerfile": dockerfile,
                "environment": environment or {},
                "depends_on": [],
                "required": True,
            }],
        }
        return definition, resolved, self.plan

    def test_secret_reference_cannot_be_baked_into_dockerfile(self):
        from unittest.mock import patch
        with patch(
            "app_catalog.services.validate_install_request",
            return_value=self._fake_catalog_materialization(
                dockerfile="FROM example/web:1\\nRUN echo " + "${secret.token}" + "\\n"
            ),
        ):
            with self.assertRaises(CatalogValidationError):
                create_application_installation(
                    self.user,
                    {"catalog_id": "hardening-fixture", "variant": "default", "name": "secret-image"},
                )

    def test_composite_secret_environment_value_is_versioned_not_plaintext(self):
        from unittest.mock import patch
        with patch(
            "app_catalog.services.validate_install_request",
            return_value=self._fake_catalog_materialization(
                environment={"DATABASE_URL": "postgres://user:" + "${secret.token}" + "@db/app"}
            ),
        ):
            instance = create_application_installation(
                self.user,
                {"catalog_id": "hardening-fixture", "variant": "default", "name": "secret-env"},
            )

        row = ServiceEnvironmentVariable.objects.get(
            service=instance.services.get(service_key="web").service,
            key="DATABASE_URL",
        )
        self.assertIsNotNone(row.secret_id)
        self.assertEqual(row.value, "")
        self.assertEqual(row.resolve_value(), "postgres://user:fixed-secret@db/app")
