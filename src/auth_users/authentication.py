"""DRF authentication for JWTs bound to revocable server-side sessions."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from .session_auth import resolve_session


class SessionJWTAuthentication(JWTAuthentication):
    """Authenticate JWTs and enforce the server-side session authority when present."""

    def authenticate(self, request):
        raw_token = self.get_raw_token(self.get_header(request))
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        session_id = validated_token.get("sid")
        if not session_id:
            return super().authenticate(request)

        user_id = validated_token.get("user_id")
        try:
            context = resolve_session(session_id, user_id=user_id)
            user = self.get_user(validated_token)
        except AuthenticationFailed:
            raise

        # Do not trust a session cache hit alone for account lifecycle state.
        # JWTAuthentication.get_user() still performs the authoritative user
        # lookup and rejects deleted/inactive users.
        if context.user_id != user.pk:
            raise AuthenticationFailed("Authentication session is invalid or revoked.")

        return user, validated_token


def resolve_user_from_access_token(raw_token):
    """Resolve bearer/query credentials for non-DRF transports."""
    try:
        validated = AccessToken(raw_token)
        user_id = validated.get("user_id") or validated.get("user")
        if not user_id:
            return None
        user = get_user_model().objects.only(
            "id", "is_active", "username"
        ).get(pk=user_id)
        if validated.get("sid"):
            resolve_session(validated["sid"], user_id=user.id)
        if not user.is_active:
            return None
        return user
    except (
        InvalidToken,
        TokenError,
        KeyError,
        get_user_model().DoesNotExist,
        AuthenticationFailed,
    ):
        return None
