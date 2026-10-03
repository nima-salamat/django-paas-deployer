from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices
from deploy.models import Deploy, DeploymentStatusChoices
from plans.models import Plan
from services.models import (
    Service,
    ServiceEndpoint,
    ServiceEnvironmentVariable,
    ServiceProcess,
    ServiceRevision,
    ServiceSecret,
    ServiceShare,
    ShellSession,
    Volume,
    DatabaseResource,
    DatabaseCredential,
    ServiceDatabaseBinding,
)
from users.models import User


class ServiceUserDeletionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="service-delete",
            email="service-delete@example.invalid",
        )
        self.target_user = User.objects.create_user(
            username="share-target",
            email="share-target@example.invalid",
        )
        self.plan = Plan.objects.create(
            name=NameChoices.BRONZE,
            platform="docker",
            plan_type=PlanTypeChoices.APP,
            max_cpu=1,
            max_ram=512,
            max_storage=10,
            price_per_hour=0,
            storage_type=StorageTypeChoices.SSD,
        )
        self.service = Service.objects.create(
            name="service-delete",
            user=self.user,
            plan=self.plan,
        )

    def test_service_owned_state_cascades_and_runtime_cleanup_signal_runs(self):
        process = ServiceProcess.objects.create(service=self.service, name="web")
        endpoint = ServiceEndpoint.objects.create(
            service=self.service,
            name="web",
            target_port=8000,
        )
        env = ServiceEnvironmentVariable.objects.create(
            service=self.service,
            key="APP_MODE",
            value="test",
        )
        secret = ServiceSecret.objects.create(
            service=self.service,
            key="APP_SECRET",
        )
        revision = ServiceRevision.objects.create(
            service=self.service,
            revision_number=1,
            config_snapshot={},
            process_snapshot=[],
            secret_keys=[],
        )
        share = ServiceShare.objects.create(
            service=self.service,
            target_user=self.target_user,
            shared_by=self.user,
            rules={"can_view": True},
        )
        shell = ShellSession.objects.create(
            service=self.service,
            user=self.user,
            token_hash="s" * 64,
            platform="docker",
            expires_at=timezone.now() + timedelta(days=3650),
        )

        with patch("services.signals.Container.exists", return_value=False), \
             patch("services.signals.Image.remove_by_name"), \
             patch("services.signals._cleanup_service_cache_images"), \
             patch("services.signals._cleanup_service_log_records"):
            self.user.delete()

        self.assertFalse(Service.objects.filter(pk=self.service.pk).exists())
        self.assertFalse(ServiceProcess.objects.filter(pk=process.pk).exists())
        self.assertFalse(ServiceEndpoint.objects.filter(pk=endpoint.pk).exists())
        self.assertFalse(ServiceEnvironmentVariable.objects.filter(pk=env.pk).exists())
        self.assertFalse(ServiceSecret.objects.filter(pk=secret.pk).exists())
        self.assertFalse(ServiceRevision.objects.filter(pk=revision.pk).exists())
        self.assertFalse(ServiceShare.objects.filter(pk=share.pk).exists())
        self.assertFalse(ShellSession.objects.filter(pk=shell.pk).exists())
        self.target_user.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=self.target_user.pk).exists())

    def test_pending_and_running_deployments_receive_cancellation_before_service_cleanup(self):
        pending = Deploy.objects.create(
            name="pending-delete",
            service=self.service,
            version=1.0,
            status=DeploymentStatusChoices.PENDING,
        )
        running = Deploy.objects.create(
            name="running-delete",
            service=self.service,
            version=2.0,
            status=DeploymentStatusChoices.RUNNING,
        )

        from services.signals import _cancel_active_deployments_for_service

        _cancel_active_deployments_for_service(self.service)

        pending.refresh_from_db()
        running.refresh_from_db()
        self.assertEqual(pending.status, DeploymentStatusChoices.CANCELLED)
        self.assertTrue(running.cancel_requested)

    def test_service_cleanup_does_not_delete_volume_when_runtime_cleanup_fails(self):
        volume = Volume.objects.create(
            name="delete-safe-volume",
            user=self.user,
            service=self.service,
            size_mb=256,
        )

        from services.signals import delete_deploy_before_delete_service

        with patch("services.signals._cancel_active_deployments_for_service"), \
             patch("services.signals.SwarmRuntime") as swarm_cls:
            swarm_cls.return_value.remove_service_group.side_effect = RuntimeError(
                "runtime failure"
            )
            with self.assertRaises(RuntimeError):
                delete_deploy_before_delete_service(Service, self.service)

        self.assertTrue(Volume.objects.filter(pk=volume.pk).exists())

    def test_database_resource_children_are_removed_with_user_but_no_unrelated_service(self):
        database = DatabaseResource.objects.create(
            owner=self.user,
            name="owned-db",
            engine=DatabaseResource.Engine.POSTGRESQL,
            status="ready",
        )
        credential = DatabaseCredential.objects.create(
            database=database,
            username="app",
            password_ciphertext="cipher",
        )
        binding = ServiceDatabaseBinding.objects.create(
            service=self.service,
            database=database,
            alias="default",
        )

        with patch("services.signals.Container.exists", return_value=False), \
             patch("services.signals.Image.remove_by_name"), \
             patch("services.signals._cleanup_service_cache_images"), \
             patch("services.signals._cleanup_service_log_records"):
            self.user.delete()

        self.assertFalse(DatabaseResource.objects.filter(pk=database.pk).exists())
        self.assertFalse(DatabaseCredential.objects.filter(pk=credential.pk).exists())
        self.assertFalse(ServiceDatabaseBinding.objects.filter(pk=binding.pk).exists())
