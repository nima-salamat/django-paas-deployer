from __future__ import annotations

from datetime import timedelta

from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

from auth_users.models import LoginSettings, UserSession
from auth_users.services import issue_tokens_for_user
from auth_users.token_serializers import SessionTokenRefreshSerializer, SessionTokenVerifySerializer
from users.models import User


@override_settings(
    SIMPLE_JWT={
        "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
        "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
        "ROTATE_REFRESH_TOKENS": True,
        "BLACKLIST_AFTER_ROTATION": True,
        "SIGNING_KEY": "token-contract-test-key",
        "ALGORITHM": "HS256",
        "USER_ID_FIELD": "id",
        "USER_ID_CLAIM": "user_id",
        "JTI_CLAIM": "jti",
    }
)
class SessionTokenSerializerContractTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="token-contract-user",
            email="token-contract@example.com",
            password="password123",
        )
        LoginSettings.objects.create(max_active_sessions=5)

    def test_refresh_requires_session_binding_claims(self):
        token = RefreshToken.for_user(self.user)
        raw = str(token)

        serializer = SessionTokenRefreshSerializer(data={"refresh": raw})
        with self.assertRaises(AuthenticationFailed):
            serializer.is_valid(raise_exception=True)

    def test_verify_rejects_access_token_without_session_claim(self):
        token = RefreshToken.for_user(self.user).access_token
        serializer = SessionTokenVerifySerializer(data={"token": str(token)})

        with self.assertRaises(AuthenticationFailed):
            serializer.is_valid(raise_exception=True)

    def test_refresh_rotates_credential_hash_and_preserves_session_id(self):
        tokens = issue_tokens_for_user(self.user)
        original_session_id = tokens["session_id"]

        serializer = SessionTokenRefreshSerializer(data={"refresh": tokens["refresh"]})
        self.assertTrue(serializer.is_valid(raise_exception=True))
        rotated = RefreshToken(serializer.validated_data["refresh"])

        self.assertEqual(str(rotated["sid"]), original_session_id)
        session = UserSession.objects.get(session_id=original_session_id)
        self.assertNotEqual(
            session.credential_hash,
            tokens["refresh"],
        )

    def test_expired_session_cannot_be_resolved_for_refresh(self):
        tokens = issue_tokens_for_user(self.user)
        UserSession.objects.filter(
            session_id=tokens["session_id"]
        ).update(expires_at=timezone.now() - timedelta(seconds=1))

        serializer = SessionTokenRefreshSerializer(data={"refresh": tokens["refresh"]})
        with self.assertRaises(AuthenticationFailed):
            serializer.is_valid(raise_exception=True)
