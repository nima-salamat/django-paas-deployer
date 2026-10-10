from rest_framework.test import APIRequestFactory, force_authenticate
from django.test import TestCase

from app_catalog.models import ApplicationInstance, ApplicationInstanceService
from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices
from deploy.models import Deploy
from plans.models import Plan
from services.api.configuration import ServiceDatabaseBindingsAPIView
from services.models import Service, ServiceEnvironmentVariable
from users.models import User


class ReadyAppDatabaseDependencyApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="ready-app-db-settings",
            email="ready-app-db-settings@example.invalid",
        )
        common = {
            "max_cpu": 1,
            "max_ram": 1024,
            "max_storage": 10,
            "price_per_hour": 0,
            "storage_type": StorageTypeChoices.SSD,
        }
        cls.app_plan = Plan.objects.create(
            name=NameChoices.BRONZE,
            platform="docker",
            plan_type=PlanTypeChoices.APP,
            **common,
        )
        cls.database_plan = Plan.objects.create(
            name=NameChoices.BRONZE,
            platform="mariadb",
            plan_type=PlanTypeChoices.DB,
            **common,
        )

    def test_database_api_reports_ready_app_database_dependency_separately_from_bindings(self):
        instance = ApplicationInstance.objects.create(
            user=self.user,
            name="WordPress",
            slug="wordpress-db-settings",
            catalog_id="wordpress",
            definition_version="1.0",
            software_version="7.1.2",
            variant_id="default",
            definition_snapshot={
                "_application_orchestration": {
                    "services": [
                        {
                            "key": "wordpress",
                            "role": "application",
                            "plan_type": str(PlanTypeChoices.APP),
                            "depends_on": ["mariadb"],
                        },
                        {
                            "key": "mariadb",
                            "role": "database",
                            "plan_type": str(PlanTypeChoices.DB),
                            "depends_on": [],
                        },
                    ],
                },
            },
        )
        app_service = Service.objects.create(
            name="wp-app-db-settings",
            user=self.user,
            plan=self.app_plan,
            source_kind=Service.SourceKind.CATALOG,
            source_config={
                "application_instance": str(instance.pk),
                "catalog_id": "wordpress",
                "service_key": "wordpress",
            },
        )
        database_service = Service.objects.create(
            name="wp-mariadb-settings",
            user=self.user,
            plan=self.database_plan,
            source_kind=Service.SourceKind.CATALOG,
            source_config={
                "application_instance": str(instance.pk),
                "catalog_id": "wordpress",
                "service_key": "mariadb",
            },
        )
        database_env = ServiceEnvironmentVariable.objects.create(
            service=database_service,
            key="MYSQL_DATABASE",
            value="wordpress",
        )
        app_deploy = Deploy.objects.create(
            name="wp-app-settings-deploy",
            service=app_service,
            created_by=self.user,
            version=1.0,
        )
        database_deploy = Deploy.objects.create(
            name="wp-db-settings-deploy",
            service=database_service,
            created_by=self.user,
            version=1.0,
        )
        ApplicationInstanceService.objects.create(
            instance=instance,
            service=app_service,
            deploy=app_deploy,
            service_key="wordpress",
            sequence=0,
        )
        ApplicationInstanceService.objects.create(
            instance=instance,
            service=database_service,
            deploy=database_deploy,
            service_key="mariadb",
            sequence=1,
        )

        request = APIRequestFactory().get(
            f"/services/service/{app_service.pk}/databases/"
        )
        force_authenticate(request, user=self.user)
        response = ServiceDatabaseBindingsAPIView.as_view()(
            request,
            service_id=app_service.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])
        self.assertEqual(len(response.data["catalog_dependencies"]), 1)
        dependency = response.data["catalog_dependencies"][0]
        self.assertEqual(dependency["service_id"], str(database_service.pk))
        self.assertEqual(dependency["service_key"], "mariadb")
        self.assertEqual(dependency["engine"], "mariadb")
        self.assertEqual(dependency["host"], "mariadb")
        self.assertEqual(dependency["port"], 3306)
        self.assertEqual(dependency["database_name"], database_env.value)
        self.assertEqual(dependency["connection_type"], "ready_app_dependency")
        self.assertNotIn("password", dependency)
        self.assertNotIn("username", dependency)

    def test_database_api_does_not_expose_catalog_siblings_to_shared_viewers(self):
        instance = ApplicationInstance.objects.create(
            user=self.user,
            name="WordPress",
            slug="wordpress-db-settings-shared",
            catalog_id="wordpress",
            definition_version="1.0",
            software_version="7.1.2",
            variant_id="default",
            definition_snapshot={
                "_application_orchestration": {
                    "services": [
                        {
                            "key": "wordpress",
                            "plan_type": str(PlanTypeChoices.APP),
                            "depends_on": ["mariadb"],
                        },
                        {
                            "key": "mariadb",
                            "plan_type": str(PlanTypeChoices.DB),
                            "depends_on": [],
                        },
                    ],
                },
            },
        )
        app_service = Service.objects.create(
            name="wp-app-db-shared",
            user=self.user,
            plan=self.app_plan,
            source_kind=Service.SourceKind.CATALOG,
            source_config={"application_instance": str(instance.pk), "service_key": "wordpress"},
        )
        db_service = Service.objects.create(
            name="wp-db-db-shared",
            user=self.user,
            plan=self.database_plan,
            source_kind=Service.SourceKind.CATALOG,
            source_config={"application_instance": str(instance.pk), "service_key": "mariadb"},
        )
        app_deploy = Deploy.objects.create(name="wp-app-shared-deploy", service=app_service, version=1.0)
        db_deploy = Deploy.objects.create(name="wp-db-shared-deploy", service=db_service, version=1.0)
        ApplicationInstanceService.objects.create(instance=instance, service=app_service, deploy=app_deploy, service_key="wordpress")
        ApplicationInstanceService.objects.create(instance=instance, service=db_service, deploy=db_deploy, service_key="mariadb")

        other_user = User.objects.create_user(
            username="ready-app-db-reader",
            email="ready-app-db-reader@example.invalid",
        )
        request = APIRequestFactory().get(f"/services/service/{app_service.pk}/databases/")
        force_authenticate(request, user=other_user)

        # This method only returns catalog dependencies for the owner. Normal
        # service-view authorization remains the API's responsibility.
        result = ServiceDatabaseBindingsAPIView._catalog_database_dependencies(
            request,
            app_service,
        )
        self.assertEqual(result, [])
