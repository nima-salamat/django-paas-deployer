from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from app_catalog.apis import (
    ApplicationInstanceStartAPIView,
    ApplicationInstanceStopAPIView,
)
from app_catalog.executor import ApplicationStackExecutor
from app_catalog.models import ApplicationInstance, ApplicationStatus
from app_catalog.services import create_application_installation
from app_catalog.tasks import _continue_application_stop, advance_application_stop
from core.global_settings.config import (
    NameChoices,
    PlanTypeChoices,
    SERVICE_STATUS_CHOICES,
    StorageTypeChoices,
)
from deploy.models import DeploymentStatusChoices
from plans.models import Plan
from services.models import Service
from users.models import User


class ReadyAppRuntimeControlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="ready-app-runtime-controls",
            email="ready-app-runtime-controls@example.invalid",
        )
        common = dict(
            max_cpu=2.0,
            max_ram=4096,
            max_storage=64,
            price_per_hour=0,
            storage_type=StorageTypeChoices.SSD,
        )
        cls.app_plan = Plan.objects.create(
            name=NameChoices.BRONZE,
            platform="docker",
            plan_type=PlanTypeChoices.APP,
            **common,
        )
        cls.db_plan = Plan.objects.create(
            name=NameChoices.BRONZE,
            platform="mariadb",
            plan_type=PlanTypeChoices.DB,
            **common,
        )

    def request(self, method, path):
        request = getattr(APIRequestFactory(), method.lower())(path, data={}, format="json")
        force_authenticate(request, user=self.user)
        return request

    def install_wordpress(self, name):
        return create_application_installation(
            self.user,
            {
                "catalog_id": "wordpress",
                "variant": "default",
                "name": name,
                "service_plan_ids": {
                    "wordpress": str(self.app_plan.pk),
                    "mariadb": str(self.db_plan.pk),
                },
                "config": {},
            },
            require_public=True,
        )

    def set_children(self, instance, *, status, desired_state, deploy_status):
        for binding in instance.services.select_related("service", "deploy"):
            Service.objects.filter(pk=binding.service_id).update(
                status=status,
                desired_state=desired_state,
                task_id=None,
                deploy_started=None,
            )
            type(binding.deploy).objects.filter(pk=binding.deploy_id).update(
                status=deploy_status,
                cancel_requested=False,
                execution_task_id="",
            )

    def test_start_all_queues_children_as_one_parent_operation(self):
        instance = self.install_wordpress("runtime-start-api")
        self.set_children(
            instance,
            status=SERVICE_STATUS_CHOICES.STOPPED,
            desired_state="stopped",
            deploy_status=DeploymentStatusChoices.SUCCEEDED,
        )
        ApplicationInstance.objects.filter(pk=instance.pk).update(
            status=ApplicationStatus.STOPPED,
            stage="application_stopped",
        )

        with patch("app_catalog.apis.start_application_runtime.delay") as enqueue:
            response = ApplicationInstanceStartAPIView.as_view()(
                self.request("POST", f"/api/application-catalog/installations/{instance.pk}/start/"),
                pk=instance.pk,
            )

        self.assertEqual(response.status_code, 202)
        instance.refresh_from_db()
        self.assertEqual(instance.status, ApplicationStatus.DEPLOYING)
        self.assertEqual(instance.runtime_operation, "start")
        self.assertEqual(instance.stage, "starting_services")
        enqueue.assert_called_once_with(str(instance.pk), instance.runtime_operation_generation)

        for binding in instance.services.select_related("service", "deploy"):
            binding.service.refresh_from_db()
            binding.deploy.refresh_from_db()
            self.assertEqual(binding.service.status, SERVICE_STATUS_CHOICES.QUEUED)
            self.assertEqual(binding.service.desired_state, "running")
            self.assertEqual(binding.deploy.status, DeploymentStatusChoices.PENDING)
            self.assertEqual(
                binding.deploy.expected_lifecycle_generation,
                binding.service.lifecycle_generation,
            )

    def test_stop_all_queues_a_persisted_parent_stop_operation(self):
        instance = self.install_wordpress("runtime-stop-api")
        self.set_children(
            instance,
            status=SERVICE_STATUS_CHOICES.RUNNING,
            desired_state="running",
            deploy_status=DeploymentStatusChoices.SUCCEEDED,
        )
        ApplicationInstance.objects.filter(pk=instance.pk).update(
            status=ApplicationStatus.RUNNING,
            stage="application_ready",
        )

        with patch("app_catalog.apis.stop_application_runtime.delay") as enqueue:
            response = ApplicationInstanceStopAPIView.as_view()(
                self.request("POST", f"/api/application-catalog/installations/{instance.pk}/stop/"),
                pk=instance.pk,
            )

        self.assertEqual(response.status_code, 202)
        instance.refresh_from_db()
        self.assertEqual(instance.status, ApplicationStatus.STOPPING)
        self.assertEqual(instance.runtime_operation, "stop")
        self.assertEqual(instance.stage, "stopping_services")
        enqueue.assert_called_once_with(str(instance.pk), instance.runtime_operation_generation)

    def test_stop_all_stops_dependents_before_their_dependencies(self):
        instance = self.install_wordpress("runtime-stop-order")
        self.set_children(
            instance,
            status=SERVICE_STATUS_CHOICES.RUNNING,
            desired_state="running",
            deploy_status=DeploymentStatusChoices.SUCCEEDED,
        )
        ApplicationInstance.objects.filter(pk=instance.pk).update(
            status=ApplicationStatus.STOPPING,
            stage="stopping_services",
            runtime_operation="stop",
            runtime_operation_generation=7,
        )

        _loaded, plan = ApplicationStackExecutor(str(instance.pk))._load()
        expected_order = tuple(reversed(plan.topological_order()))
        expected_services = {
            row.service_key: row.service_id
            for row in instance.services.all()
        }

        with patch("app_catalog.tasks.stop_service_task.apply_async") as enqueue:
            first = _continue_application_stop(str(instance.pk), 7)
            self.assertEqual(first["dispatched"], expected_order[0])
            self.assertEqual(
                enqueue.call_args.kwargs["args"],
                [str(expected_services[expected_order[0]])],
            )

            first_service = Service.objects.get(pk=expected_services[expected_order[0]])
            first_service.status = SERVICE_STATUS_CHOICES.STOPPED
            first_service.desired_state = "stopped"
            first_service.save(update_fields=["status", "desired_state"])

            advance_application_stop.run(str(instance.pk), expected_order[0], 7)
            self.assertEqual(enqueue.call_count, 2)
            self.assertEqual(
                enqueue.call_args.kwargs["args"],
                [str(expected_services[expected_order[1]])],
            )

            second_service = Service.objects.get(pk=expected_services[expected_order[1]])
            second_service.status = SERVICE_STATUS_CHOICES.STOPPED
            second_service.desired_state = "stopped"
            second_service.save(update_fields=["status", "desired_state"])

            advance_application_stop.run(str(instance.pk), expected_order[1], 7)

        instance.refresh_from_db()
        self.assertEqual(instance.status, ApplicationStatus.STOPPED)
        self.assertEqual(instance.stage, "application_stopped")
        self.assertEqual(instance.runtime_operation, "")

    def test_runtime_operations_reject_deletion_pending_installations(self):
        instance = self.install_wordpress("runtime-deleting")
        ApplicationInstance.objects.filter(pk=instance.pk).update(
            stage="deletion_pending",
            status=ApplicationStatus.STOPPED,
        )
        response = ApplicationInstanceStartAPIView.as_view()(
            self.request("POST", f"/api/application-catalog/installations/{instance.pk}/start/"),
            pk=instance.pk,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "application_deletion_pending")
