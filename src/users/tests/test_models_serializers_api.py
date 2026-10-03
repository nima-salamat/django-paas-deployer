from __future__ import annotations

import io
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from users.models import Profile, Receipt, Rule
from users.serializers import (
    ChangePasswordSerializer,
    CreateUserSerializer,
    SetPasswordSerializer,
    UpdateUserSerializer,
)

User = get_user_model()


def image_file(name="avatar.jpg"):
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


class UserModelAndSerializerTests(TestCase):
    def test_user_has_unique_uuid_and_rule_is_one_to_one(self):
        user = User.objects.create_user(username="alice", email="a@example.com", password="password123")
        Rule.objects.create(user=user, rules=["plans.view"])

        self.assertEqual(User.objects.filter(uuid=user.uuid).count(), 1)
        self.assertEqual(user.rule.rules, ["plans.view"])

    def test_receipt_change_balance_marks_payment_and_updates_balance(self):
        user = User.objects.create_user(username="payer", email="p@example.com", password="password123")
        receipt = Receipt.objects.create(user=user, amount="125.500")

        Receipt.change_balance(receipt)

        user.refresh_from_db()
        receipt.refresh_from_db()
        self.assertEqual(str(user.balance), "125.500")
        self.assertEqual(receipt.status, "PAYED")

    def test_profile_limit_is_five(self):
        user = User.objects.create_user(username="profile-owner", email="profile@example.com", password="password123")
        for index in range(5):
            Profile.objects.create(user=user, order=index, image=image_file(f"{index}.jpg"))

        sixth = Profile(user=user, order=6, image=image_file("sixth.jpg"))
        with self.assertRaises(Exception):
            sixth.save()

    def test_create_user_serializer_requires_an_identifier(self):
        serializer = CreateUserSerializer(data={"username": "new-user"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)

    def test_set_password_serializer_rejects_mismatched_passwords(self):
        serializer = SetPasswordSerializer(
            data={"new_password": "password123", "new_confirm_password": "different123"}
        )
        self.assertFalse(serializer.is_valid())

    def test_change_password_serializer_rejects_wrong_current_password(self):
        user = User.objects.create_user(username="pw-user", email="pw@example.com", password="correct123")
        serializer = ChangePasswordSerializer(
            user=user,
            data={
                "current_password": "wrong123",
                "new_password": "newcorrect123",
                "new_confirm_password": "newcorrect123",
            },
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)

    def test_update_user_serializer_blocks_direct_contact_changes(self):
        serializer = UpdateUserSerializer(
            data={"email": "new@example.com", "theme": "light", "color": 1}
        )
        self.assertFalse(serializer.is_valid())


class UserAPIPermissionAndCacheTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="api-user",
            email="api@example.com",
            password="password123",
        )
        self.staff = User.objects.create_user(
            username="api-staff",
            email="staff@example.com",
            password="password123",
            is_staff=True,
        )
        self.other = User.objects.create_user(
            username="api-other",
            email="other@example.com",
            password="password123",
        )

    def test_user_profile_endpoint_requires_authentication(self):
        self.assertIn(self.client.get("/api/users/user/").status_code, (401, 403))

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/users/user/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "api-user")

    def test_user_update_rejects_contact_change_outside_otp_flow(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.put(
            "/api/users/user/",
            {
                "email": "changed@example.com",
                "theme": "dark",
                "color": self.user.color,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_admin_permission_catalog_requires_users_view_rule(self):
        self.client.force_authenticate(user=self.staff)
        denied = self.client.get("/api/users/admin/permissions/")
        self.assertEqual(denied.status_code, 403)

        Rule.objects.create(user=self.staff, rules=["users.view"])
        allowed = self.client.get("/api/users/admin/permissions/")
        self.assertEqual(allowed.status_code, 200)
        self.assertIn("plans.manage", allowed.json()["data"]["permissions"])

    def test_admin_user_create_rule_is_narrow(self):
        Rule.objects.create(user=self.staff, rules=["users.view", "users.create"])
        self.client.force_authenticate(user=self.staff)

        response = self.client.post(
            "/api/users/admin/users/",
            {
                "username": "created-limited",
                "email": "limited@example.com",
                "password": "password123",
                "is_staff": True,
                "is_superuser": True,
                "rules": ["plans.manage"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        created = User.objects.get(username="created-limited")
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)
        self.assertEqual(created.rule.rules, [])

    def test_user_admin_cache_signal_is_triggered_for_rule_changes(self):
        Rule.objects.create(user=self.staff, rules=["users.view"])
        with patch("core.app_cache.invalidate_all_users_admin") as invalidate:
            Rule.objects.get(user=self.staff).save()
        invalidate.assert_called()
