from datetime import timedelta
import uuid

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User
from .models import Device, LoginSettings, UserSession
from .services import SessionLimitExceeded, issue_tokens_for_user
from .session_auth import invalidate_session, resolve_session, session_cache_key
from django.core.cache import cache


@override_settings(
    SIMPLE_JWT={
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
        "SIGNING_KEY": "session-test-key",
        "ALGORITHM": "HS256",
        "USER_ID_FIELD": "id",
        "USER_ID_CLAIM": "user_id",
        "JTI_CLAIM": "jti",
    }
)
class UserSessionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="session-user", email="session@example.test", password="pass12345"
        )
        LoginSettings.objects.create(
            max_active_sessions=2,
            session_eviction_policy=LoginSettings.SessionEvictionPolicy.REVOKE_OLDEST,
        )

    def test_issue_creates_device_session_and_binds_token_identity(self):
        tokens = issue_tokens_for_user(self.user, device_id="12345678-1234-5678-1234-567812345678")

        session = UserSession.objects.get(session_id=tokens["session_id"])
        device = Device.objects.get(pk=session.device_id)
        access = RefreshToken(tokens["refresh"]).access_token

        self.assertEqual(session.user_id, self.user.id)
        self.assertEqual(device.public_id, uuid.UUID("12345678-1234-5678-1234-567812345678"))
        self.assertEqual(access["sid"], session.session_id)
        self.assertNotEqual(session.credential_hash, tokens["refresh"])
        self.assertTrue(session.is_active)

    def test_limit_revokes_oldest_active_session_transactionally(self):
        first = issue_tokens_for_user(self.user)
        first_session = UserSession.objects.get(session_id=first["session_id"])
        UserSession.objects.filter(pk=first_session.pk).update(
            created_at=timezone.now() - timedelta(minutes=5)
        )

        issue_tokens_for_user(self.user)
        issue_tokens_for_user(self.user)

        first_session.refresh_from_db()
        self.assertIsNotNone(first_session.revoked_at)
        self.assertEqual(
            UserSession.objects.filter(user=self.user, revoked_at__isnull=True).count(), 2
        )

    def test_reject_policy_does_not_create_a_fourth_session(self):
        LoginSettings.objects.update(
            session_eviction_policy=LoginSettings.SessionEvictionPolicy.REJECT_NEW
        )
        issue_tokens_for_user(self.user)
        issue_tokens_for_user(self.user)

        with self.assertRaises(SessionLimitExceeded):
            issue_tokens_for_user(self.user)

        self.assertEqual(UserSession.objects.filter(user=self.user).count(), 2)

    def test_cache_hit_and_explicit_invalidation_block_replay(self):
        tokens = issue_tokens_for_user(self.user)
        session_id = tokens["session_id"]

        context = resolve_session(session_id, user_id=self.user.id)
        self.assertEqual(context.session_id, session_id)
        self.assertIsNotNone(cache.get(session_cache_key(session_id)))

        self.assertTrue(invalidate_session(session_id))
        with self.assertRaises(Exception):
            resolve_session(session_id, user_id=self.user.id)
        self.assertIsNone(cache.get(session_cache_key(session_id)))
