from __future__ import annotations

from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from deploy.models import BuildCacheQuota, Deploy
from deploy.serializers import DeploySerializer

from plans.models import Plan
from services.models import PrivateNetwork, Service

User = get_user_model()


class DeployModelAndSerializerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="deploy-owner", email="deploy@example.com", password="password123")
        self.plan = Plan.objects.create(
            name="Bronze",
            platform="docker",
            plan_type="APP",
            max_cpu=1,
            max_ram=512,
            max_storage=10,
            price_per_hour=1,
            storage_type="SSD",
        )
        self.network = PrivateNetwork.objects.create(user=self.user, name="deploy-net")
        self.service = Service.objects.create(
            name="deploy-service",
            user=self.user,
            plan=self.plan,
            network=self.network,
        )

    def test_build_cache_quota_requires_exactly_one_owner(self):
        user_only = BuildCacheQuota(user=self.user, quota_mb=128)
        user_only.full_clean()

        none = BuildCacheQuota(quota_mb=128)
        with self.assertRaises(ValidationError):
            none.full_clean()

        both = BuildCacheQuota(user=self.user, service=self.service, quota_mb=128)
        with self.assertRaises(ValidationError):
            both.full_clean()

    def test_deploy_lifecycle_deadline_uses_application_phase(self):
        started = timezone.now() - timedelta(minutes=5)
        deploy = Deploy(
            name="deploy-1",
            service=self.service,
            application_started_at=started,
            stage="application",
        )
        deadline = deploy.lifecycle_phase_deadline(
            base_timeout_minutes=20,
            application_timeout_minutes=10,
        )
        self.assertEqual(deadline, started + timedelta(minutes=10))

    def test_deploy_serializer_marks_runtime_state_read_only(self):
        fields = DeploySerializer().fields
        for name in (
            "status",
            "stage",
            "progress",
            "health_status",
            "container_status",
            "rollback_status",
            "recent_logs",
            "created_at",
        ):
            self.assertTrue(fields[name].read_only)

    def test_deploy_serializer_refuses_editing_revision_bound_execution_config(self):
        deploy = Deploy.objects.create(
            name="revision-bound",
            service=self.service,
            revision_id=None,
        )
        # The serializer contract uses presence of revision_id as the immutable
        # execution snapshot fence; exercise the validator without requiring a
        # concrete ServiceRevision fixture.
        deploy.revision_id = "00000000-0000-0000-0000-000000000001"
        serializer = DeploySerializer(
            instance=deploy,
            data={"version": 2},
            partial=True,
        )
        # version alone is mutable; executable fields are protected.
        self.assertTrue(serializer.is_valid(), serializer.errors)

        serializer = DeploySerializer(
            instance=deploy,
            data={"config": {"platform": "docker"}},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("revision", serializer.errors)

    def test_masked_db_config_hides_sensitive_keys_for_non_owner(self):
        class Request:
            def __init__(self, user):
                self.user = user

        deploy = Deploy(
            name="masked",
            service=self.service,
            config={"platform": "postgresql", "password": "secret", "host": "db"},
        )
        stranger = User.objects.create_user(username="deploy-stranger", email="stranger@example.com", password="password123")
        serializer = DeploySerializer(
            deploy,
            context={"request": Request(stranger)},
        )
        data = serializer.data
        self.assertNotIn("secret", str(data["config"]))

    def test_deploy_model_rejects_oversized_zip_without_operator_override(self):
        deploy = Deploy(
            name="oversized",
            service=self.service,
        )
        fake_file = Mock(size=Deploy.MAX_ZIP_SIZE_MB * 1024 * 1024 + 1)
        deploy.zip_file = fake_file
        with self.assertRaises(ValidationError):
            deploy.full_clean()

