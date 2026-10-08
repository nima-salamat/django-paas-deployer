"""Real Docker/Celery integration tests.

Run only in the project's normal development/integration environment with:
    RUN_DEPLOYMENT_INTEGRATION=1 pytest -m deployment_integration -q app_catalog/tests/integration

The test deliberately uses the real Django ORM and Celery broker. It does not
invoke docker compose to deploy the application under test.
"""
from __future__ import annotations

import os
import time

import pytest

pytestmark = pytest.mark.deployment_integration

if os.getenv("RUN_DEPLOYMENT_INTEGRATION") != "1":
    pytest.skip("Set RUN_DEPLOYMENT_INTEGRATION=1 to run real Docker/Celery integration tests", allow_module_level=True)

pytest.importorskip("django")
pytest.importorskip("celery")
pytest.importorskip("docker")

from django.test import TestCase
from app_catalog.models import ApplicationInstance, ApplicationStatus
from app_catalog.services import create_application_installation
from app_catalog.tasks import start_application_installation
from plans.models import Plan
from users.models import User
from core.global_settings.config import PlanTypeChoices, StorageTypeChoices


class ReadyApplicationRuntimeTests(TestCase):
    def _plans(self):
        common = {
            "max_cpu": 2.0,
            "max_ram": 4096,
            "max_storage": 20,
            "price_per_hour": 0,
            "storage_type": StorageTypeChoices.SSD,
        }
        app, _ = Plan.objects.get_or_create(
            name="Bronze", platform="docker", plan_type=PlanTypeChoices.APP,
            defaults=common,
        )
        Plan.objects.get_or_create(
            name="Bronze", platform="postgresql", plan_type=PlanTypeChoices.DB,
            defaults=common,
        )
        Plan.objects.get_or_create(
            name="Bronze", platform="mariadb", plan_type=PlanTypeChoices.DB,
            defaults=common,
        )
        return app

    def test_wordpress_mariadb_real_stack(self):
        user = User.objects.create_user(
            username="runtime-wordpress-integration",
            email="runtime-wordpress-integration@example.invalid",
        )
        app_plan = self._plans()
        instance = create_application_installation(
            user,
            {
                "catalog_id": "wordpress",
                "variant": "default",
                "name": "runtime-wordpress",
                "plan_id": app_plan.pk,
                "config": {
                    "domain": "wordpress.integration.test",
                    "wordpress_site_title": "Runtime WordPress Integration",
                    "wordpress_admin_user": "runtime-admin",
                    "wordpress_admin_email": "runtime-wordpress-integration@example.invalid",
                    "wordpress_admin_password": "runtime-admin-password-123",
                    "wordpress_table_prefix": "wp_",
                },
            },
        )

        start_application_installation.delay(str(instance.pk))

        deadline = time.monotonic() + int(os.getenv("DEPLOYMENT_INTEGRATION_TIMEOUT", "900"))
        while time.monotonic() < deadline:
            instance.refresh_from_db()
            if instance.status in {
                ApplicationStatus.RUNNING,
                ApplicationStatus.FAILED,
                ApplicationStatus.CANCELLED,
            }:
                break
            time.sleep(3)

        instance.refresh_from_db()
        self.assertEqual(instance.status, ApplicationStatus.RUNNING, instance.error_message)
        statuses = {b.service_key: b.deploy.status for b in instance.services.select_related("deploy")}
        self.assertEqual(statuses.get("mariadb"), "succeeded")
        self.assertEqual(statuses.get("wordpress"), "succeeded")

        wordpress_binding = next(
            binding
            for binding in instance.services.select_related("service", "deploy")
            if binding.service_key == "wordpress"
        )
        from deployments.core.manager.client_manager import get_docker_client

        client = get_docker_client()
        swarm_service = client.services.get(wordpress_binding.service.get_docker_service_name())
        container_spec = (
            (swarm_service.attrs.get("Spec") or {})
            .get("TaskTemplate", {})
            .get("ContainerSpec", {})
        )
        self.assertIsNone(container_spec.get("Command"))
        self.assertEqual(
            container_spec.get("Args"),
            [
                "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
                "/usr/local/bin/apache2-foreground",
            ],
        )

        tasks = swarm_service.tasks()
        running_tasks = [
            task for task in tasks
            if str(task.get("Status", {}).get("State") or "").lower() == "running"
        ]
        self.assertTrue(running_tasks, "WordPress Swarm service has no running task.")
        container_id = str(
            (running_tasks[0].get("Status", {}).get("ContainerStatus") or {}).get("ContainerID") or ""
        )
        self.assertTrue(container_id, "Running WordPress task has no container ID.")
        container = client.containers.get(container_id)
        container.reload()
        health = ((container.attrs.get("State") or {}).get("Health") or {}).get("Status")
        self.assertEqual(health, "healthy")
        result = container.exec_run(["wp", "core", "is-installed", "--allow-root"])
        self.assertEqual(result.exit_code, 0, result.output.decode(errors="replace"))

    def test_mattermost_postgres_real_stack(self):
        user = User.objects.create_user(
            username="runtime-integration",
            email="runtime-integration@example.invalid",
        )
        app_plan = self._plans()
        instance = create_application_installation(
            user,
            {
                "catalog_id": "mattermost",
                "variant": "postgresql",
                "name": "runtime-mattermost",
                "plan_id": app_plan.pk,
                "config": {
                    "domain": "mattermost.integration.test",
                    "storage_mb": 4096,
                },
            },
        )

        start_application_installation.delay(str(instance.pk))

        deadline = time.monotonic() + int(os.getenv("DEPLOYMENT_INTEGRATION_TIMEOUT", "900"))
        while time.monotonic() < deadline:
            instance.refresh_from_db()
            if instance.status in {
                ApplicationStatus.RUNNING,
                ApplicationStatus.FAILED,
                ApplicationStatus.CANCELLED,
            }:
                break
            time.sleep(3)

        instance.refresh_from_db()
        self.assertEqual(instance.status, ApplicationStatus.RUNNING, instance.error_message)
        statuses = {b.service_key: b.deploy.status for b in instance.services.select_related("deploy")}
        self.assertEqual(statuses.get("postgres"), "succeeded")
        self.assertEqual(statuses.get("mattermost"), "succeeded")
