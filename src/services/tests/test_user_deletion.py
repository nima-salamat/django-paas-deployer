from unittest.mock import patch

from django.test import TestCase

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
)
from users.models import User
from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices


class ServiceUserDeletionTests(TestCase):
    def test_service_owned_state_cascades_and_runtime_cleanup_signal_runs(self):
        user = User.objects.create_user(username="service-delete", email="service-delete@example.invalid")
        plan = Plan.objects.create(
            name=NameChoices.BRONZE,
            platform="docker",
            plan_type=PlanTypeChoices.APP,
            max_cpu=1,
            max_ram=512,
            max_storage=10,
            price_per_hour=0,
            storage_type=StorageTypeChoices.SSD,
        )
        service = Service.objects.create(name="service-delete", user=user, plan=plan)
        process = ServiceProcess.objects.create(service=service, name="web")
        endpoint = ServiceEndpoint.objects.create(service=service, name="web", target_port=8000)
        env = ServiceEnvironmentVariable.objects.create(service=service, key="APP_MODE", value="test")
        secret = ServiceSecret.objects.create(service=service, key="APP_SECRET")
        revision = ServiceRevision.objects.create(
            service=service,
            revision_number=1,
            config_snapshot={},
            process_snapshot=[],
            secret_keys=[],
        )
        share = ServiceShare.objects.create(
            service=service,
            target_user=User.objects.create_user(username="share-target", email="share-target@example.invalid"),
            rules={"view": True},
        )
        shell = ShellSession.objects.create(
            service=service,
            user=user,
            platform="docker",
            expires_at="2099-01-01T00:00:00Z",
        )

        with patch("services.signals.Container.exists", return_value=False),              patch("services.signals.Image.remove_by_name"),              patch("services.signals._cleanup_service_cache_images"),              patch("services.signals._cleanup_service_log_records"):
            user.delete()

        self.assertFalse(Service.objects.filter(pk=service.pk).exists())
        self.assertFalse(ServiceProcess.objects.filter(pk=process.pk).exists())
        self.assertFalse(ServiceEndpoint.objects.filter(pk=endpoint.pk).exists())
        self.assertFalse(ServiceEnvironmentVariable.objects.filter(pk=env.pk).exists())
        self.assertFalse(ServiceSecret.objects.filter(pk=secret.pk).exists())
        self.assertFalse(ServiceRevision.objects.filter(pk=revision.pk).exists())
        self.assertFalse(ServiceShare.objects.filter(pk=share.pk).exists())
        self.assertFalse(ShellSession.objects.filter(pk=shell.pk).exists())
