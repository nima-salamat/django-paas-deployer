import base64
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile

from users.models import Profile, Rule, User, Receipt


class UserDeletionTests(TestCase):
    def test_profile_and_user_owned_rows_are_removed(self):
        user = User.objects.create_user(
            username="delete-user-owned",
            email="delete-user-owned@example.invalid",
        )
        Rule.objects.create(user=user)
        Receipt.objects.create(user=user, amount="10.000")

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            profile = Profile.objects.create(
                user=user,
                order=1,
                image=SimpleUploadedFile(
                    "profile.png",
                    base64.b64decode(
                        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                    ),
                    content_type="image/png",
                ),
            )
            path = Path(profile.image.path)
            self.assertTrue(path.exists())

            with patch("services.lifecycle.mark_deleted"):
                user.delete()

            self.assertFalse(path.exists())

        self.assertFalse(Profile.objects.filter(user_id=user.pk).exists())
        self.assertFalse(Rule.objects.filter(user_id=user.pk).exists())
        self.assertFalse(Receipt.objects.filter(user_id=user.pk).exists())

    def test_user_signal_marks_services_for_deleted_lifecycle(self):
        from plans.models import Plan
        from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices
        from services.models import Service
        from users.signals import cleanup_user_resources

        user = User.objects.create_user(
            username="delete-user-fence",
            email="delete-user-fence@example.invalid",
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
        service = Service.objects.create(name="delete-fence", user=user, plan=plan)

        with patch("services.lifecycle.mark_deleted") as mark_deleted:
            cleanup_user_resources(User, user)
            mark_deleted.assert_called_once_with(service.pk)

    def test_generic_table_browser_cannot_bypass_critical_deletion_boundaries(self):
        from users.admin_tables_api import TABLE_REGISTRY

        self.assertFalse(TABLE_REGISTRY["users.User"]["deletable"])
        self.assertFalse(TABLE_REGISTRY["plans.Plan"]["deletable"])
        self.assertFalse(TABLE_REGISTRY["deploy.Deploy"]["deletable"])
        self.assertFalse(TABLE_REGISTRY["deploy.DeployLog"]["deletable"])
        self.assertFalse(TABLE_REGISTRY["custom_emails.EmailTemplate"]["deletable"])


    def test_direct_user_delete_is_blocked_when_owned_deploy_is_active(self):
        from deploy.models import Deploy, DeploymentStatusChoices
        from plans.models import Plan
        from services.models import Service
        from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices

        user = User.objects.create_user(
            username="delete-live-deploy",
            email="delete-live-deploy@example.invalid",
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
        service = Service.objects.create(name="live-delete-service", user=user, plan=plan)
        deploy = Deploy.objects.create(
            name="live-delete-deploy",
            service=service,
            created_by=user,
            version=1,
            status=DeploymentStatusChoices.RUNNING,
        )

        with self.assertRaises(RuntimeError):
            user.delete()

        self.assertTrue(User.objects.filter(pk=user.pk).exists())
        deploy.refresh_from_db()
        self.assertEqual(deploy.status, DeploymentStatusChoices.RUNNING)

    def test_hard_delete_request_deactivates_and_queues_convergence(self):
        from deploy.models import Deploy, DeploymentStatusChoices
        from plans.models import Plan
        from services.models import Service
        from rest_framework.test import APIRequestFactory, force_authenticate
        from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices

        operator = User.objects.create_superuser(
            username="deletion-operator",
            email="deletion-operator@example.invalid",
            password="operator-password",
        )
        user = User.objects.create_user(
            username="delete-queued",
            email="delete-queued@example.invalid",
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
        service = Service.objects.create(name="queued-delete-service", user=user, plan=plan)
        Deploy.objects.create(
            name="queued-delete-deploy",
            service=service,
            created_by=user,
            version=1,
            status=DeploymentStatusChoices.RUNNING,
        )

        from users.admin_apis import AdminUserDetailAPIView

        request = APIRequestFactory().delete(
            f"/api/users/admin/users/{user.pk}/?hard=1"
        )
        force_authenticate(request, user=operator)

        with patch("users.tasks.request_user_deletion_convergence"),              patch("users.tasks.finalize_user_deletion.delay"):
            response = AdminUserDetailAPIView.as_view()(request, pk=user.pk)

        self.assertEqual(response.status_code, 202)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertIsNotNone(user.deletion_requested_at)
        self.assertTrue(User.objects.filter(pk=user.pk).exists())
