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
        return app

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
