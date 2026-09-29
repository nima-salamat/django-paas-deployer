"""DRF authentication requiring JWTs bound to revocable server-side sessions."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from .session_auth import resolve_session


class SessionJWTAuthentication(JWTAuthentication):
    """Authenticate only JWTs bound to an active server-side session."""

    def authenticate(self, request):
        header = self.get_header(request)
        if header is None:
            return None

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self._authenticate_validated_token(validated_token)

    def _authenticate_validated_token(self, validated_token):
        session_id = validated_token.get("sid")
        if not session_id:
            raise AuthenticationFailed("Authentication session is required.")

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


def get_session_id_from_access_token(raw_token):
    """Return the session id embedded in a validated access JWT."""
    try:
        validated = AccessToken(raw_token)
        session_id = validated.get("sid")
        return str(session_id) if session_id else None
    except (InvalidToken, TokenError, KeyError):
        return None


def resolve_user_from_access_token(raw_token):
    """Resolve bearer/query credentials for non-DRF transports."""
    try:
        validated = AccessToken(raw_token)
        session_id = validated.get("sid")
        if not session_id:
            return None

        user_id = validated.get("user_id") or validated.get("user")
        if not user_id:
            return None

        resolve_session(session_id, user_id=user_id)
        user = get_user_model().objects.only(
            "id", "is_active", "username"
        ).get(pk=user_id)
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
