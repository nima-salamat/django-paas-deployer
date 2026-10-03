from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from auth_users.models import AuthCode
from users.models import Rule

User = get_user_model()


class AuthAdminRulePermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="auth-rule-staff",
            email="auth-rule-staff@example.com",
            password="password123",
            is_staff=True,
        )

    def test_invite_admin_requires_invites_manage(self):
        self.client.force_authenticate(user=self.staff)
        self.assertEqual(self.client.get("/auth/api/invite/list/").status_code, 403)

        Rule.objects.create(user=self.staff, rules=["invites.manage"])
        self.assertEqual(self.client.get("/auth/api/invite/list/").status_code, 200)

    def test_auth_code_read_requires_view_or_manage(self):
        AuthCode.objects.create(contact="otp@example.com", code="abc123")
        self.client.force_authenticate(user=self.staff)

        self.assertEqual(self.client.get("/auth/api/admin/auth-codes/").status_code, 403)

        Rule.objects.create(user=self.staff, rules=["auth_codes.view"])
        response = self.client.get("/auth/api/admin/auth-codes/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["count"], 1)

    def test_auth_code_delete_and_purge_require_manage(self):
        code = AuthCode.objects.create(contact="delete@example.com", code="delete")
        self.client.force_authenticate(user=self.staff)
        Rule.objects.create(user=self.staff, rules=["auth_codes.view"])

        self.assertEqual(
            self.client.delete(f"/auth/api/admin/auth-codes/{code.pk}/").status_code,
            403,
        )

        rule = Rule.objects.get(user=self.staff)
        rule.rules = ["auth_codes.view", "auth_codes.manage"]
        rule.save()

        self.assertEqual(
            self.client.delete(f"/auth/api/admin/auth-codes/{code.pk}/").status_code,
            200,
        )
        self.assertFalse(AuthCode.objects.filter(pk=code.pk).exists())
        self.assertEqual(
            self.client.post("/auth/api/admin/auth-codes/purge/").status_code,
            200,
        )

    def test_superuser_bypasses_auth_admin_rules(self):
        superuser = User.objects.create_superuser(
            username="auth-rule-super",
            email="auth-rule-super@example.com",
            password="password123",
        )
        self.client.force_authenticate(user=superuser)
        self.assertEqual(self.client.get("/auth/api/invite/list/").status_code, 200)
        self.assertEqual(self.client.get("/auth/api/admin/auth-codes/").status_code, 200)
