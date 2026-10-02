from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile

from users.models import Profile, Rule, User, Receipt
from services.models import ServiceNetworkAttachment


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
                image=SimpleUploadedFile("profile.jpg", b"profile-bytes", content_type="image/jpeg"),
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

        with patch("services.lifecycle.mark_deleted") as mark_deleted,              patch("users.signals.ServiceNetworkAttachment.objects.filter") as attachment_filter:
            attachment_filter.return_value.exclude.return_value.values_list.return_value = []
            cleanup_user_resources(User, user)
            mark_deleted.assert_called_once_with(service.pk)
