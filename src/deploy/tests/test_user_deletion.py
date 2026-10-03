from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from deploy.models import BuildCacheArtifact, Deploy, DeploymentStatusChoices
from plans.models import Plan
from services.models import Service
from users.models import User
from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices


class DeployUserDeletionTests(TestCase):
    def test_service_owned_deploy_archive_and_cache_records_are_removed(self):
        user = User.objects.create_user(username="deploy-delete", email="deploy-delete@example.invalid")
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
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            service = Service.objects.create(name="deploy-delete-service", user=user, plan=plan)
            deploy = Deploy.objects.create(
                name="deploy-delete-1",
                service=service,
                created_by=user,
                version=1.0,
                zip_file=SimpleUploadedFile("source.zip", b"zip-bytes"),
            )
            artifact = BuildCacheArtifact.objects.create(
                deployment=deploy,
                user=user,
                service=service,
                image_ref="deploy-delete-service:1",
                image_id="sha256:" + "d" * 64,
                image_digest="",
                size_bytes=1024,
            )
            path = Path(deploy.zip_file.path)
            self.assertTrue(path.exists())

            with patch("services.signals.Container.exists", return_value=False),                  patch("services.signals.Image.remove_by_name"),                  patch("services.signals._cleanup_service_cache_images"),                  patch("services.signals._cleanup_service_log_records"):
                user.delete()

            self.assertFalse(path.exists())

        self.assertFalse(Deploy.objects.filter(pk=deploy.pk).exists())
        self.assertFalse(BuildCacheArtifact.objects.filter(pk=artifact.pk).exists())

    def test_active_deploy_cannot_be_deleted_directly(self):
        user = User.objects.create_user(
            username="deploy-active-delete",
            email="deploy-active-delete@example.invalid",
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
        service = Service.objects.create(
            name="deploy-active-delete-service",
            user=user,
            plan=plan,
        )
        deploy = Deploy.objects.create(
            name="deploy-active-delete-1",
            service=service,
            created_by=user,
            version=1.0,
            status=DeploymentStatusChoices.RUNNING,
        )

        from deploy.apis import DeployViewSet

        request = APIRequestFactory().delete(f"/deploy/{deploy.pk}/")
        force_authenticate(request, user=user)
        response = DeployViewSet.as_view({"delete": "destroy"})(request, pk=deploy.pk)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "deployment_active_requires_cancel")
        self.assertTrue(Deploy.objects.filter(pk=deploy.pk).exists())

    def test_deploy_delete_releases_base_runtime_image_leases(self):
        from deploy.base_images import release_base_image_leases
        from deploy.models import BaseRuntimeImage, BaseRuntimeImageLease

        image = BaseRuntimeImage.objects.create(
            logical_runtime="node",
            runtime_version="22",
            variant="default",
            source_image="node:22",
            image_repository="paas-base/node",
            image_tag="22-r1",
            image_ref="paas-base/node:22-r1",
        )
        deploy = Deploy.objects.create(
            name="lease-delete",
            service=Service.objects.create(
                name="lease-delete-service",
                user=User.objects.create_user(
                    username="lease-delete-user",
                    email="lease-delete-user@example.invalid",
                ),
                plan=Plan.objects.create(
                    name=NameChoices.SILVER,
                    platform="docker",
                    plan_type=PlanTypeChoices.APP,
                    max_cpu=1,
                    max_ram=512,
                    max_storage=10,
                    price_per_hour=0,
                    storage_type=StorageTypeChoices.SSD,
                ),
            ),
            version=1.0,
        )
        lease = BaseRuntimeImageLease.objects.create(
            base_image=image,
            deployment_id=str(deploy.pk),
        )

        deploy.delete()

        lease.refresh_from_db()
        self.assertIsNotNone(lease.released_at)
