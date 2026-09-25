"""DRF authentication that understands server-side session-bound JWTs."""
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model

from .session_auth import resolve_session


class SessionJWTAuthentication(JWTAuthentication):
    """Validate JWT cryptography, then enforce a revocable session when present.

    Tokens issued before the migration do not carry ``sid`` and continue
    through the legacy JWT path until the compatibility window is retired.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, validated_token = result
        session_id = validated_token.get("sid")
        if not session_id:
            return result
        try:
            resolve_session(session_id, user_id=user.pk)
        except AuthenticationFailed:
            raise
        return user, validated_token


def resolve_user_from_access_token(raw_token):
    """Resolve bearer/query credentials for non-DRF transports."""
    try:
        validated = AccessToken(raw_token)
        user_id = validated.get("user_id") or validated.get("user")
        if not user_id:
            return None
        user = get_user_model().objects.only("id", "is_active", "username").get(pk=user_id)
        if validated.get("sid"):
            resolve_session(validated["sid"], user_id=user.id)
        if not user.is_active:
            return None
        return user
    except (InvalidToken, TokenError, KeyError, get_user_model().DoesNotExist, AuthenticationFailed):
        return None
