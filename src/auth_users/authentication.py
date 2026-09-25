"""DRF authentication that understands server-side session-bound JWTs."""
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

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
