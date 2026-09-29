from datetime import timedelta
import hashlib
import uuid

from django.test import TestCase, override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from users.models import User
from .models import Device, LoginSettings, UserSession
from .services import SessionLimitExceeded, issue_tokens_for_user
from .authentication import resolve_user_from_access_token
from .session_auth import (
    invalidate_session,
    resolve_session,
    session_cache_key,
)
from .token_serializers import (
    SessionTokenRefreshSerializer,
    SessionTokenVerifySerializer,
)
from django.core.cache import cache


@override_settings(
    SIMPLE_JWT={
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
        "ROTATE_REFRESH_TOKENS": True,
        "BLACKLIST_AFTER_ROTATION": True,
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
        with self.assertRaises(AuthenticationFailed):
            resolve_session(session_id, user_id=self.user.id)
        self.assertIsNone(cache.get(session_cache_key(session_id)))

    def test_second_session_resolution_is_cache_hit_without_database_queries(self):
        tokens = issue_tokens_for_user(self.user)
        session_id = tokens["session_id"]

        resolve_session(session_id, user_id=self.user.id)
        with CaptureQueriesContext(connection) as queries:
            context = resolve_session(session_id, user_id=self.user.id)

        self.assertEqual(context.session_id, session_id)
        self.assertEqual(len(queries), 0)

    def test_session_eviction_removes_the_old_session_cache_entry(self):
        LoginSettings.objects.update(max_active_sessions=1)
        first = issue_tokens_for_user(self.user)
        first_session_id = first["session_id"]
        resolve_session(first_session_id, user_id=self.user.id)
        self.assertIsNotNone(cache.get(session_cache_key(first_session_id)))

        issue_tokens_for_user(self.user)

        self.assertIsNone(cache.get(session_cache_key(first_session_id)))
        with self.assertRaises(AuthenticationFailed):
            resolve_session(first_session_id, user_id=self.user.id)

    def test_refresh_rotation_rejects_reuse_of_previous_refresh_token(self):
        tokens = issue_tokens_for_user(self.user)
        serializer = SessionTokenRefreshSerializer(data={"refresh": tokens["refresh"]})

        first = serializer.is_valid(raise_exception=True)
        self.assertIn("refresh", first)

        reused = SessionTokenRefreshSerializer(data={"refresh": tokens["refresh"]})
        with self.assertRaises(AuthenticationFailed):
            reused.is_valid(raise_exception=True)

    def test_refresh_rotation_preserves_session_binding(self):
        tokens = issue_tokens_for_user(self.user)
        session_id = tokens["session_id"]

        serializer = SessionTokenRefreshSerializer(data={"refresh": tokens["refresh"]})
        data = serializer.is_valid(raise_exception=True)

        rotated = RefreshToken(data["refresh"])
        self.assertEqual(str(rotated["sid"]), session_id)
        self.assertEqual(
            UserSession.objects.get(session_id=session_id).credential_hash,
            hashlib.sha256(data["refresh"].encode("utf-8")).hexdigest(),
        )

    def test_token_verify_rejects_a_revoked_session(self):
        tokens = issue_tokens_for_user(self.user)
        serializer = SessionTokenVerifySerializer(data={"token": tokens["access"]})
        serializer.is_valid(raise_exception=True)

        invalidate_session(tokens["session_id"])

        revoked = SessionTokenVerifySerializer(data={"token": tokens["access"]})
        with self.assertRaises(AuthenticationFailed):
            revoked.is_valid(raise_exception=True)


    def test_revoked_session_is_rejected_by_an_authenticated_api_endpoint(self):
        tokens = issue_tokens_for_user(self.user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        first = client.get("/api/users/user/")
        self.assertEqual(first.status_code, 200)

        invalidate_session(tokens["session_id"])

        second = client.get("/api/users/user/")
        self.assertEqual(second.status_code, 401)

    def _client_for(self, access_token):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        return client

    def test_young_session_cannot_revoke_another_session(self):
        first = issue_tokens_for_user(
            self.user,
            device_id="00000000-0000-0000-0000-000000000001",
        )
        second = issue_tokens_for_user(
            self.user,
            device_id="00000000-0000-0000-0000-000000000002",
        )

        client = self._client_for(second["access"])
        response = client.delete(f"/auth/api/sessions/{first['session_id']}/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            UserSession.objects.filter(
                user=self.user,
                revoked_at__isnull=True,
            ).count(),
            2,
        )

    def test_young_session_can_revoke_itself(self):
        tokens = issue_tokens_for_user(self.user)
        client = self._client_for(tokens["access"])

        response = client.delete(f"/auth/api/sessions/{tokens['session_id']}/")

        self.assertEqual(response.status_code, 204)
        self.assertIsNotNone(
            UserSession.objects.get(session_id=tokens["session_id"]).revoked_at
        )

    def test_young_session_cannot_logout_other_sessions(self):
        issue_tokens_for_user(self.user)
        second = issue_tokens_for_user(self.user)

        client = self._client_for(second["access"])
        response = client.post("/auth/api/sessions/logout-all/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            UserSession.objects.filter(
                user=self.user,
                revoked_at__isnull=True,
            ).count(),
            2,
        )

    def test_mature_session_can_logout_all_sessions(self):
        issue_tokens_for_user(self.user)
        second = issue_tokens_for_user(self.user)
        UserSession.objects.filter(
            session_id=second["session_id"]
        ).update(
            created_at=timezone.now() - timedelta(hours=2, seconds=1)
        )

        client = self._client_for(second["access"])
        response = client.post("/auth/api/sessions/logout-all/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["revoked"], 2)

    def test_young_session_cannot_revoke_another_device(self):
        first = issue_tokens_for_user(
            self.user,
            device_id="00000000-0000-0000-0000-000000000011",
        )
        second = issue_tokens_for_user(
            self.user,
            device_id="00000000-0000-0000-0000-000000000012",
        )

        client = self._client_for(second["access"])
        response = client.delete(
            "/auth/api/devices/00000000-0000-0000-0000-000000000011/sessions/"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            UserSession.objects.filter(
                user=self.user,
                device__public_id="00000000-0000-0000-0000-000000000011",
                revoked_at__isnull=True,
            ).count(),
            1,
        )

    def test_mature_session_can_revoke_another_device(self):
        issue_tokens_for_user(
            self.user,
            device_id="00000000-0000-0000-0000-000000000021",
        )
        second = issue_tokens_for_user(
            self.user,
            device_id="00000000-0000-0000-0000-000000000022",
        )
        UserSession.objects.filter(
            session_id=second["session_id"]
        ).update(
            created_at=timezone.now() - timedelta(hours=2, seconds=1)
        )

        client = self._client_for(second["access"])
        response = client.delete(
            "/auth/api/devices/00000000-0000-0000-0000-000000000021/sessions/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["revoked"], 1)

    def test_young_session_cannot_revoke_sibling_session_on_same_device(self):
        device_id = "00000000-0000-0000-0000-000000000031"
        issue_tokens_for_user(self.user, device_id=device_id)
        second = issue_tokens_for_user(self.user, device_id=device_id)

        client = self._client_for(second["access"])
        response = client.delete(f"/auth/api/devices/{device_id}/sessions/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            UserSession.objects.filter(
                user=self.user,
                device__public_id=device_id,
                revoked_at__isnull=True,
            ).count(),
            2,
        )


    def test_anonymous_authenticated_request_returns_401_instead_of_server_error(self):
        client = APIClient()
        response = client.get("/api/users/user/")
        self.assertEqual(response.status_code, 401)

    def test_public_login_settings_ignores_stale_legacy_authorization_header(self):
        legacy_refresh = RefreshToken.for_user(self.user)
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {legacy_refresh.access_token}"
        )

        response = client.get("/auth/api/settings/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("settings", response.data)

    def test_legacy_access_token_is_rejected_everywhere(self):
        legacy_refresh = RefreshToken.for_user(self.user)
        legacy_access = str(legacy_refresh.access_token)

        self.assertIsNone(resolve_user_from_access_token(legacy_access))

        client = self._client_for(legacy_access)
        response = client.get("/api/users/user/")

        self.assertEqual(response.status_code, 401)

    def test_legacy_refresh_token_is_rejected(self):
        legacy_refresh = RefreshToken.for_user(self.user)

        serializer = SessionTokenRefreshSerializer(
            data={"refresh": str(legacy_refresh)}
        )

        with self.assertRaises(AuthenticationFailed):
            serializer.is_valid(raise_exception=True)

    def test_legacy_token_verify_is_rejected(self):
        legacy_refresh = RefreshToken.for_user(self.user)
        legacy_access = str(legacy_refresh.access_token)

        serializer = SessionTokenVerifySerializer(
            data={"token": legacy_access}
        )

        with self.assertRaises(AuthenticationFailed):
            serializer.is_valid(raise_exception=True)

    def test_legacy_session_token_cannot_authenticate_non_drf_media_helper(self):
        legacy_refresh = RefreshToken.for_user(self.user)
        legacy_access = str(legacy_refresh.access_token)

        self.assertIsNone(resolve_user_from_access_token(legacy_access))
