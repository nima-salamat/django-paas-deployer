from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from auth_users.models import (
    AuthCode,
    Device,
    InviteLink,
    InviteUsage,
    LoginSettings,
    UserContactChange,
    UserSession,
)
from users.models import Rule
from django.contrib.auth import get_user_model

User = get_user_model()


class AuthModelInvariantTests(TestCase):
    def test_login_settings_singleton_keeps_only_one_active_row(self):
        first = LoginSettings.objects.create(is_active=True)
        second = LoginSettings.objects.create(is_active=True)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)
        self.assertIs(LoginSettings.get_solo(), second)

    def test_login_settings_rejects_disabling_all_identifiers(self):
        settings = LoginSettings(
            allow_username=False,
            allow_email=False,
            allow_phone=False,
        )
        with self.assertRaises(ValidationError):
            settings.full_clean()

    def test_login_settings_rejects_disabling_otp_and_password(self):
        settings = LoginSettings(
            require_otp=False,
            require_password=False,
        )
        with self.assertRaises(ValidationError):
            settings.full_clean()

    def test_invite_usage_and_remaining_uses_are_consistent(self):
        owner = User.objects.create_user(username="invite-owner", email="invite@example.com", password="password123")
        invite = InviteLink.objects.create(created_by=owner, max_uses=2)
        target = User.objects.create_user(username="invite-target", email="target@example.com", password="password123")

        self.assertTrue(invite.is_valid())
        self.assertEqual(invite.remaining_uses(), 2)

        invite.consume(target)
        invite.refresh_from_db()

        self.assertEqual(invite.uses_count, 1)
        self.assertEqual(invite.remaining_uses(), 1)
        self.assertTrue(InviteUsage.objects.filter(invite=invite, user=target).exists())

    def test_expired_invite_is_invalid_and_cannot_be_consumed(self):
        owner = User.objects.create_user(username="expired-owner", email="expired@example.com", password="password123")
        target = User.objects.create_user(username="expired-target", email="expired-target@example.com", password="password123")
        invite = InviteLink.objects.create(
            created_by=owner,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertFalse(invite.is_valid())
        with self.assertRaises(ValidationError):
            invite.consume(target)

    def test_auth_code_attempts_lock_after_configured_limit(self):
        user = User.objects.create_user(username="otp-user", email="otp@example.com", password="password123")
        LoginSettings.objects.create(otp_max_attempts=2)

        code = AuthCode.create_or_refresh(
            user=user,
            purpose=AuthCode.PURPOSE_LOGIN,
        )
        AuthCode.validate(user=user, code="wrong", purpose=AuthCode.PURPOSE_LOGIN)
        code.refresh_from_db()
        self.assertEqual(code.attempts, 1)
        AuthCode.validate(user=user, code="wrong", purpose=AuthCode.PURPOSE_LOGIN)
        code.refresh_from_db()
        self.assertTrue(code.is_locked())

    def test_user_session_active_state_and_revoke(self):
        user = User.objects.create_user(username="session-user", email="session@example.com", password="password123")
        device = Device.objects.create(user=user, client="Chrome")
        session = UserSession.objects.create(
            session_id="session-test-1",
            user=user,
            device=device,
            credential_hash="hash",
            expires_at=timezone.now() + timedelta(hours=1),
        )

        self.assertTrue(session.is_active)
        session.revoke()
        session.save()
        session.refresh_from_db()
        self.assertFalse(session.is_active)


class AuthAdminPermissionAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="auth-admin",
            email="auth-admin@example.com",
            password="password123",
            is_staff=True,
        )

    def test_public_login_settings_are_readable(self):
        LoginSettings.objects.create()
        response = self.client.get("/auth/api/settings/")
        self.assertEqual(response.status_code, 200)

    def test_admin_login_settings_need_view_rule_for_read(self):
        LoginSettings.objects.create()
        self.client.force_authenticate(user=self.staff)

        denied = self.client.get("/auth/api/admin/login-settings/")
        self.assertEqual(denied.status_code, 403)

        Rule.objects.create(user=self.staff, rules=["login_settings.view"])
        allowed = self.client.get("/auth/api/admin/login-settings/")
        self.assertEqual(allowed.status_code, 200)

    def test_admin_login_settings_need_manage_rule_for_mutation(self):
        settings = LoginSettings.objects.create()
        self.client.force_authenticate(user=self.staff)

        Rule.objects.create(user=self.staff, rules=["login_settings.view"])
        denied = self.client.patch(
            "/auth/api/admin/login-settings/",
            {"min_password_length": 10},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        staff_rule = Rule.objects.get(user=self.staff)
        staff_rule.rules = ["login_settings.view", "login_settings.manage"]
        staff_rule.save()

        allowed = self.client.patch(
            "/auth/api/admin/login-settings/",
            {"min_password_length": 10},
            format="json",
        )
        self.assertEqual(allowed.status_code, 200)
        settings.refresh_from_db()
        self.assertEqual(settings.min_password_length, 10)
