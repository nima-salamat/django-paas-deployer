from datetime import timedelta

from django.test import TestCase
from unittest.mock import patch
from django.utils import timezone

from auth_users.models import AuthCode, Device, InviteLink, InviteUsage, LoginLog, UserContactChange, UserSession
from users.models import User


class AuthUserDeletionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="auth-delete",
            email="auth-delete@example.invalid",
        )

    def test_security_state_cascades_but_audit_log_is_retained(self):
        device = Device.objects.create(user=self.user, name="browser")
        session = UserSession.objects.create(
            user=self.user,
            device=device,
            session_id="session-delete-1",
            credential_hash="hash",
            expires_at=timezone.now() + timedelta(days=3650),
        )
        contact = UserContactChange.objects.create(
            user=self.user,
            field=UserContactChange.Field.EMAIL,
            new_value="new@example.invalid",
        )
        code = AuthCode.objects.create(
            user=self.user,
            code="12345678",
        )
        invite = InviteLink.objects.create(created_by=self.user, label="created by deleted user")
        usage = InviteUsage.objects.create(invite=invite, user=self.user)
        log = LoginLog.objects.create(
            user=self.user,
            username=self.user.username,
            identifier=self.user.email,
        )

        uid = self.user.pk
        self.user.delete()

        self.assertFalse(Device.objects.filter(pk=device.pk).exists())
        self.assertFalse(UserSession.objects.filter(pk=session.pk).exists())
        self.assertFalse(UserContactChange.objects.filter(pk=contact.pk).exists())
        self.assertFalse(AuthCode.objects.filter(pk=code.pk).exists())
        self.assertFalse(InviteUsage.objects.filter(pk=usage.pk).exists())

        invite.refresh_from_db()
        self.assertIsNone(invite.created_by_id)
        log.refresh_from_db()
        self.assertIsNone(log.user_id)
        self.assertEqual(log.username, "auth-delete")
        self.assertFalse(User.objects.filter(pk=uid).exists())

    def test_user_delete_invalidates_session_cache_after_commit(self):
        device = Device.objects.create(user=self.user, name="cache-browser")
        session = UserSession.objects.create(
            user=self.user,
            device=device,
            session_id="session-cache-delete",
            credential_hash="hash",
            expires_at=timezone.now() + timedelta(days=3650),
        )

        with patch("auth_users.session_auth._delete_session_cache_keys") as delete_cache:
            with self.captureOnCommitCallbacks(execute=True):
                self.user.delete()

        delete_cache.assert_called_once_with([session.session_id])
