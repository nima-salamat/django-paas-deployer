from unittest.mock import patch

from django.test import TestCase

from app_catalog.models import ApplicationInstance, ApplicationInstanceService
from app_catalog.user_deletion import prepare_user_hard_delete
from plans.models import Plan
from services.models import PrivateNetwork, Service
from deploy.models import Deploy
from users.models import User
from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices


class AppCatalogUserDeletionTests(TestCase):
    def test_hard_delete_preparation_removes_binding_before_child_service_delete(self):
        user = User.objects.create_user(
            username="catalog-user-delete",
            email="catalog-user-delete@example.invalid",
        )
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
        network = PrivateNetwork.objects.create(user=user, name="catalog-delete-net")
        instance = ApplicationInstance.objects.create(
            user=user,
            name="catalog-delete",
            slug="catalog-delete",
            catalog_id="mattermost",
            definition_version="1",
            software_version="1",
            variant_id="default",
            definition_snapshot={"_application_orchestration": {"services": [{"key": "app"}]}},
            network=network,
            status="failed",
        )
        service = Service.objects.create(
            name="catalog-delete-service",
            user=user,
            plan=plan,
            network=network,
            source_kind=Service.SourceKind.CATALOG,
            source_config={"application_instance": str(instance.pk)},
        )
        deploy = Deploy.objects.create(
            name="catalog-delete-deploy",
            service=service,
            created_by=user,
            version=1.0,
        )
        binding = ApplicationInstanceService.objects.create(
            instance=instance,
            service=service,
            deploy=deploy,
            service_key="app",
        )

        with patch.object(Service, "delete") as service_delete,              patch.object(PrivateNetwork, "delete") as network_delete:
            prepare_user_hard_delete(user)

        service.refresh_from_db()
        deploy.refresh_from_db()
        self.assertEqual(service.desired_state, "deleted")
        self.assertTrue(deploy.cancel_requested)
        service_delete.assert_called_once_with()
        network_delete.assert_called_once_with()
        self.assertFalse(ApplicationInstanceService.objects.filter(pk=binding.pk).exists())
