from django.test import TestCase

from app_catalog.executor import ApplicationStackExecutor
from app_catalog.models import ApplicationInstance, ApplicationInstanceService, ApplicationStatus
from deploy.models import Deploy, DeploymentStatusChoices
from plans.models import Plan
from services.models import PrivateNetwork, Service
from users.models import User
from core.global_settings.config import PlanTypeChoices, StorageTypeChoices


class ReadyAppRuntimeSupervisorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="ready-app-supervisor",
            email="ready-app-supervisor@example.invalid",
        )
        cls.plan = Plan.objects.create(
            name="Supervisor Docker",
            platform="docker",
            plan_type=PlanTypeChoices.APP,
            max_cpu=2.0,
            max_ram=4096,
            max_storage=20,
            price_per_hour=0,
            storage_type=StorageTypeChoices.SSD,
        )

    def _application(self):
        network = PrivateNetwork.objects.create(
            name="supervisor-network",
            user=self.user,
        )
        instance = ApplicationInstance.objects.create(
            user=self.user,
            name="supervised-app",
            slug="supervised-app",
            catalog_id="supervisor-fixture",
            definition_version="1",
            software_version="1",
            variant_id="default",
            definition_snapshot={
                "_application_orchestration": {
                    "services": [
                        {
                            "key": "web",
                            "role": "app",
                            "platform": "docker",
                            "plan_type": "APP",
                            "depends_on": [],
                            "required": True,
                        }
                    ]
                }
            },
            config={},
            secret_config={},
            status=ApplicationStatus.RUNNING,
            stage="application_ready",
            deployed_at=__import__("django.utils.timezone", fromlist=["now"]).now(),
            network=network,
        )
        service = Service.objects.create(
            name="supervised-web",
            user=self.user,
            plan=self.plan,
            network=network,
            status="running",
            desired_state="running",
            source_kind=Service.SourceKind.CATALOG,
            source_config={"application_instance": str(instance.pk)},
        )
        deploy = Deploy.objects.create(
            name="supervised-web-deploy",
            service=service,
            created_by=self.user,
            status=DeploymentStatusChoices.SUCCEEDED,
            stage="deployment_completed",
            progress=100,
            status_message="Deployment succeeded.",
        )
        ApplicationInstanceService.objects.create(
            instance=instance,
            service=service,
            deploy=deploy,
            service_key="web",
            sequence=0,
        )
        return instance, service, deploy, network

    def test_healthy_running_application_is_reconciled_as_ready(self):
        instance, _service, _deploy, _network = self._application()
        instance.stage = "runtime_reconciling"
        instance.error_code = "APPLICATION_RUNTIME_DEGRADED"
        instance.error_message = "Temporary stale observation."
        instance.save(update_fields=["stage", "error_code", "error_message", "updated_at"])

        result = ApplicationStackExecutor(str(instance.pk)).supervise_runtime()

        instance.refresh_from_db()
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(instance.status, ApplicationStatus.RUNNING)
        self.assertEqual(instance.stage, "application_ready")
        self.assertEqual(instance.error_code, "")
        self.assertEqual(instance.error_message, "")

    def test_unhealthy_required_child_is_recorded_as_degraded_without_hiding_running_state(self):
        instance, service, deploy, _network = self._application()
        deploy.status = DeploymentStatusChoices.FAILED
        deploy.save(update_fields=["status", "updated_at"])
        service.status = "failed"
        service.save(update_fields=["status", "updated_at"])

        result = ApplicationStackExecutor(str(instance.pk)).supervise_runtime()

        instance.refresh_from_db()
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(instance.status, ApplicationStatus.RUNNING)
        self.assertEqual(instance.stage, "runtime_reconciling")
        self.assertEqual(instance.error_code, "APPLICATION_RUNTIME_DEGRADED")
        self.assertIn("required child deployment is failed", instance.error_message)

    def test_structural_application_corruption_fails_closed(self):
        instance, _service, _deploy, _network = self._application()
        ApplicationInstanceService.objects.filter(instance=instance).delete()

        result = ApplicationStackExecutor(str(instance.pk)).supervise_runtime()

        instance.refresh_from_db()
        self.assertEqual(result["status"], "corrupted")
        self.assertEqual(instance.status, ApplicationStatus.FAILED)
        self.assertEqual(instance.stage, "state_corrupted")
        self.assertEqual(instance.error_code, "APPLICATION_STATE_CORRUPTED")
        self.assertIn("missing child service bindings", instance.error_message)

    def test_supervisor_rejects_child_network_drift_as_structural_corruption(self):
        instance, service, _deploy, _network = self._application()
        other_network = PrivateNetwork.objects.create(
            name="supervisor-other-network",
            user=self.user,
        )
        # Direct field assignment is intentional: this test simulates persisted
        # DB drift, bypassing the normal Service catalog-ownership validation.
        Service.objects.filter(pk=service.pk).update(network_id=other_network.pk)

        result = ApplicationStackExecutor(str(instance.pk)).supervise_runtime()

        instance.refresh_from_db()
        self.assertEqual(result["status"], "corrupted")
        self.assertEqual(instance.status, ApplicationStatus.FAILED)
        self.assertEqual(instance.error_code, "APPLICATION_STATE_CORRUPTED")
        self.assertIn("different private network", instance.error_message)
