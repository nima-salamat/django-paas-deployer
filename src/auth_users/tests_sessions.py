from datetime import timedelta
import hashlib
import uuid

from django.test import TestCase, override_settings
from unittest.mock import AsyncMock, patch
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from asgiref.sync import async_to_sync
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from users.models import User
from .models import Device, LoginSettings, UserSession
from messenger.consumers import MessengerConsumer
from tickets.consumers import TicketEventsConsumer, TicketNotifyConsumer
from services.consumers import ServiceLogsConsumer, RestrictedShellConsumer
from deployments.consumers import DeploymentConsumer
from .services import SessionLimitExceeded, issue_tokens_for_user
from .authentication import (
    get_session_id_from_access_token,
    resolve_user_from_access_token,
)
from .session_auth import (
    invalidate_session,
    resolve_session,
    session_cache_key,
    _deserialize_cache_value,
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
        # Async consumer tests may leave the thread-local PostgreSQL handle closed.
        # Reset it so each TestCase starts from a reconnectable connection.
        connection.close()
        self.user = User.objects.create_user(
            username="session-user", email="session@example.test", password="pass12345"
        )
        LoginSettings.objects.create(
            max_active_sessions=2,
            session_eviction_policy=LoginSettings.SessionEvictionPolicy.REVOKE_OLDEST,
        )

    def test_cached_session_accepts_legacy_cached_at_metadata(self):
        now = timezone.now()
        cached = _deserialize_cache_value(
            {
                "session": {
                    "session_id": "legacy-session",
                    "user_id": self.user.id,
                    "device_id": "12345678-1234-5678-1234-567812345678",
                    "auth_generation": 1,
                    "expires_at": (now + timedelta(minutes=5)).isoformat(),
                    "cached_at": now.isoformat(),
                }
            }
        )

        self.assertIsNotNone(cached)
        self.assertEqual(cached.cached_at, now)
        self.assertEqual(cached.context.session_id, "legacy-session")

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


    def _legacy_access_token(self):
        return str(RefreshToken.for_user(self.user).access_token)

    def test_new_login_flow_issues_a_session_bound_token(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        LoginSettings.objects.update(
            require_otp=False,
            require_password=True,
            password_as_second_factor=False,
        )

        client = APIClient()
        response = client.post(
            "/auth/api/authentication/",
            {"username": self.user.username, "email": self.user.email},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

        access = RefreshToken(response.data["refresh"]).access_token
        self.assertEqual(str(access["sid"]), str(response.data["session_id"]))
        self.assertTrue(
            UserSession.objects.filter(
                session_id=response.data["session_id"],
                user=self.user,
                revoked_at__isnull=True,
            ).exists()
        )

    def test_all_public_auth_routes_ignore_a_stale_bearer_token(self):
        legacy_access = self._legacy_access_token()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {legacy_access}")

        cases = [
            ("get", "/auth/api/settings/", None, 200),
            ("post", "/auth/api/authentication/", {}, 400),
            ("post", "/auth/api/login/", {}, 400),
            ("post", "/auth/api/signup/", {}, 400),
            ("post", "/auth/api/login/validate/", {}, 400),
            ("post", "/auth/api/login/token/", {}, 400),
            ("post", "/auth/api/set-password/", {}, 400),
            ("post", "/auth/api/recovery/request/", {}, 400),
            ("post", "/auth/api/recovery/confirm/", {}, 400),
            ("post", "/auth/api/password-recovery/request/", {}, 400),
            ("post", "/auth/api/password-recovery/confirm/", {}, 400),
            ("get", "/auth/api/invite/validate/", None, 400),
        ]

        for method, url, body, expected in cases:
            with self.subTest(method=method, url=url):
                if body is None:
                    response = getattr(client, method)(url)
                else:
                    response = getattr(client, method)(url, data=body, format="json")
                self.assertEqual(response.status_code, expected)

    def test_validate_token_rejects_a_legacy_access_token(self):
        client = self._client_for(self._legacy_access_token())
        response = client.get("/auth/api/validateToken/")
        self.assertEqual(response.status_code, 401)

    def test_session_id_helper_rejects_legacy_token_and_accepts_new_token(self):
        self.assertIsNone(
            get_session_id_from_access_token(self._legacy_access_token())
        )
        tokens = issue_tokens_for_user(self.user)
        self.assertEqual(
            get_session_id_from_access_token(tokens["access"]),
            tokens["session_id"],
        )

    def _assert_revoked_session_ping_closes(self, consumer_cls, *, scope_mode=False):
        tokens = issue_tokens_for_user(self.user)
        session_id = tokens["session_id"]
        invalidate_session(session_id)

        consumer = consumer_cls.__new__(consumer_cls)
        consumer.user = self.user
        consumer.auth_session_id = session_id
        consumer.close = AsyncMock()
        consumer.send_json = AsyncMock()
        if scope_mode:
            consumer.scope = {"auth_session_id": session_id}

        async_to_sync(consumer.receive_json)({"type": "ping"})

        consumer.close.assert_awaited_once_with(code=4401)
        consumer.send_json.assert_not_awaited()

    def _assert_live_session_ping_returns_pong(self, consumer_cls, *, scope_mode=False):
        tokens = issue_tokens_for_user(self.user)
        session_id = tokens["session_id"]

        consumer = consumer_cls.__new__(consumer_cls)
        consumer.user = self.user
        consumer.auth_session_id = session_id
        consumer.close = AsyncMock()
        consumer.send_json = AsyncMock()
        if scope_mode:
            consumer.scope = {"auth_session_id": session_id}

        async_to_sync(consumer.receive_json)({"type": "ping"})

        consumer.close.assert_not_awaited()
        consumer.send_json.assert_awaited_once_with({"type": "pong"})

    def test_messenger_websocket_revalidates_revoked_session(self):
        self._assert_revoked_session_ping_closes(
            MessengerConsumer,
            scope_mode=True,
        )

    def test_ticket_websockets_revalidate_revoked_session(self):
        for consumer_cls in (TicketEventsConsumer, TicketNotifyConsumer):
            with self.subTest(consumer=consumer_cls.__name__):
                self._assert_revoked_session_ping_closes(consumer_cls)

    def test_service_and_deployment_websockets_revalidate_revoked_session(self):
        for consumer_cls in (ServiceLogsConsumer, RestrictedShellConsumer, DeploymentConsumer):
            with self.subTest(consumer=consumer_cls.__name__):
                self._assert_revoked_session_ping_closes(consumer_cls)

    def test_websocket_heartbeats_accept_live_sessions(self):
        self._assert_live_session_ping_returns_pong(
            MessengerConsumer,
            scope_mode=True,
        )
        for consumer_cls in (
            TicketEventsConsumer,
            TicketNotifyConsumer,
            ServiceLogsConsumer,
            RestrictedShellConsumer,
            DeploymentConsumer,
        ):
            with self.subTest(consumer=consumer_cls.__name__):
                self._assert_live_session_ping_returns_pong(consumer_cls)


    def test_non_drf_resolver_rejects_a_revoked_session_token(self):
        tokens = issue_tokens_for_user(self.user)
        self.assertEqual(
            resolve_user_from_access_token(tokens["access"]),
            self.user,
        )
        invalidate_session(tokens["session_id"])
        self.assertIsNone(
            resolve_user_from_access_token(tokens["access"])
        )

    def test_all_websocket_connections_reject_legacy_access_tokens(self):
        legacy_access = self._legacy_access_token()
        cases = [
            (MessengerConsumer, 4401, {"auth_session_id": None}),
            (TicketEventsConsumer, 4403, {}),
            (TicketNotifyConsumer, 4401, {}),
            (ServiceLogsConsumer, 4002, {}),
            (RestrictedShellConsumer, 4003, {"shell_token": "invalid"}),
            (DeploymentConsumer, 4002, {}),
        ]

        for consumer_cls, expected_code, extra_scope in cases:
            with self.subTest(consumer=consumer_cls.__name__):
                consumer = consumer_cls.__new__(consumer_cls)
                query = f"token={legacy_access}"
                for key, value in extra_scope.items():
                    if value is not None:
                        query += f"&{key}={value}"
                consumer.scope = {
                    "query_string": query.encode("utf-8"),
                    "url_route": {"kwargs": {"service_id": "1", "deploy_id": "1"}},
                }
                consumer.close = AsyncMock()

                async_to_sync(consumer.connect)()

                consumer.close.assert_awaited_once_with(code=expected_code)


    def test_exactly_two_hour_old_session_can_manage_other_sessions(self):
        from auth_users import session_auth

        first = issue_tokens_for_user(
            self.user,
            device_id="00000000-0000-0000-0000-000000000041",
        )
        second = issue_tokens_for_user(
            self.user,
            device_id="00000000-0000-0000-0000-000000000042",
        )
        management_now = timezone.now()
        UserSession.objects.filter(
            session_id=second["session_id"]
        ).update(
            created_at=management_now - timedelta(hours=2)
        )

        with patch.object(session_auth.timezone, "now", return_value=management_now):
            client = self._client_for(second["access"])
            response = client.delete(
                f"/auth/api/sessions/{first['session_id']}/"
            )

        self.assertEqual(response.status_code, 204)
        self.assertIsNotNone(
            UserSession.objects.get(
                session_id=first["session_id"]
            ).revoked_at
        )


    def test_legacy_access_token_is_rejected_by_service_detail_and_runtime_status(self):
        client = self._client_for(self._legacy_access_token())

        retrieve = client.get(
            "/services/service/00000000-0000-0000-0000-000000000001/"
        )
        status = client.post(
            "/services/service_status/",
            {"service_id": "00000000-0000-0000-0000-000000000001"},
            format="json",
        )

        self.assertEqual(retrieve.status_code, 401)
        self.assertEqual(status.status_code, 401)

    def test_session_bound_access_token_reaches_service_detail_authorization(self):
        tokens = issue_tokens_for_user(self.user)
        client = self._client_for(tokens["access"])

        response = client.get(
            "/services/service/00000000-0000-0000-0000-000000000001/"
        )

        self.assertIn(response.status_code, {404, 403})
