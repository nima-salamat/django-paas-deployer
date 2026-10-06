from django.test import TestCase
from unittest.mock import patch

from app_catalog.executor import ApplicationStackExecutor
from app_catalog.models import ApplicationInstance, ApplicationInstanceService, ApplicationStatus
from deploy.models import Deploy, DeploymentStatusChoices
from plans.models import Plan
from services.models import PrivateNetwork, Service
from users.models import User
from core.global_settings.config import PlanTypeChoices, StorageTypeChoices


class ReadyAppDeletionResilienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="ready-app-delete-resilience",
            email="ready-app-delete-resilience@example.invalid",
        )
        cls.plan = Plan.objects.create(
            name="Ready App Delete",
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
            name="delete-resilience-network",
            user=self.user,
        )
        keys = ("web", "worker", "rollback")
        instance = ApplicationInstance.objects.create(
            user=self.user,
            name="delete-resilience",
            slug="delete-resilience",
            catalog_id="delete-resilience-fixture",
            definition_version="1",
            software_version="1",
            variant_id="default",
            definition_snapshot={
                "_application_orchestration": {
                    "services": [
                        {
                            "key": key,
                            "role": "app",
                            "platform": "docker",
                            "plan_type": "APP",
                            "depends_on": [],
                            "required": True,
                        }
                        for key in keys
                    ]
                }
            },
            config={},
            status=ApplicationStatus.RUNNING,
            stage="deletion_pending",
            cancel_requested=True,
            network=network,
        )

        statuses = (
            DeploymentStatusChoices.PENDING,
            DeploymentStatusChoices.RUNNING,
            DeploymentStatusChoices.ROLLING_BACK,
        )
        for key, deploy_status in zip(keys, statuses):
            service = Service.objects.create(
                name=f"delete-resilience-{key}",
                user=self.user,
                plan=self.plan,
                network=network,
                status="running",
                desired_state="running",
                source_kind=Service.SourceKind.CATALOG,
                source_config={
                    "application_instance": str(instance.pk),
                    "service_key": key,
                    "catalog_id": instance.catalog_id,
                },
            )
            deploy = Deploy.objects.create(
                name=f"delete-resilience-{key}-deploy",
                service=service,
                created_by=self.user,
                status=deploy_status,
                cancel_requested=True,
                stage="cancellation_requested",
            )
            ApplicationInstanceService.objects.create(
                instance=instance,
                service=service,
                deploy=deploy,
                service_key=key,
                sequence=len(instance.services.all()),
            )
        return instance, network

    def test_deletion_terminalizes_pending_running_and_rollback_children_after_runtime_cleanup(self):
        instance, network = self._application()

        with (
            patch("app_catalog.executor.cleanup_service_resources"),
            patch("services.signals._cancel_active_deployments_for_service"),
            patch("services.signals._cleanup_service_log_records"),
            patch("services.signals.Network.network_exists", return_value=False),
        ):
            deleted = ApplicationStackExecutor(str(instance.pk)).cleanup_terminal_application()

        self.assertTrue(deleted)
        self.assertFalse(ApplicationInstance.objects.filter(pk=instance.pk).exists())
        self.assertFalse(Service.objects.filter(name__startswith="delete-resilience-").exists())
        self.assertFalse(
            Deploy.objects.filter(name__startswith="delete-resilience-").exists()
        )
        self.assertFalse(PrivateNetwork.objects.filter(pk=network.pk).exists())

    def test_deletion_fences_child_desired_state_before_cleanup(self):
        instance, _network = self._application()
        observed_states = []

        def observe(service):
            observed_states.append((service.pk, service.desired_state))

        with (
            patch(
                "app_catalog.executor.cleanup_service_resources",
                side_effect=observe,
            ),
            patch("services.signals._cancel_active_deployments_for_service"),
            patch("services.signals._cleanup_service_log_records"),
            patch("services.signals.Network.network_exists", return_value=False),
        ):
            ApplicationStackExecutor(str(instance.pk)).cleanup_terminal_application()

        self.assertEqual(len(observed_states), 3)
        self.assertTrue(all(state == "deleted" for _, state in observed_states))
