"""Session-aware SimpleJWT serializers."""
from __future__ import annotations

import hashlib
import hmac

from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.exceptions import (
    AuthenticationFailed,
    InvalidToken,
    TokenError,
)
from rest_framework_simplejwt.serializers import (
    TokenRefreshSerializer,
    TokenVerifySerializer,
)
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .models import UserSession
from .session_auth import (
    get_active_session_for_update,
    cache_session,
    resolve_session,
)


class SessionTokenRefreshSerializer(TokenRefreshSerializer):
    """Rotate a refresh credential only when it is still the session's current credential."""

    def validate(self, attrs):
        raw_refresh = attrs.get("refresh")
        try:
            refresh = RefreshToken(raw_refresh)
            session_id = refresh.get("sid")
            user_id = refresh.get("user_id")

            if not session_id:
                # Legacy tokens remain compatible during the migration window.
                return super().validate(attrs)
            if not user_id:
                raise AuthenticationFailed(
                    "Authentication session is invalid or revoked."
                )

            incoming_hash = hashlib.sha256(
                str(raw_refresh).encode("utf-8")
            ).hexdigest()

            with transaction.atomic():
                session = get_active_session_for_update(
                    str(session_id),
                    user_id=user_id,
                )
                if not hmac.compare_digest(
                    incoming_hash,
                    str(session.credential_hash),
                ):
                    raise AuthenticationFailed(
                        "Refresh token has already been rotated or revoked."
                    )

                data = super().validate(attrs)
                new_refresh = data.get("refresh")
                if not new_refresh:
                    raise AuthenticationFailed(
                        "Refresh token rotation did not return a new credential."
                    )

                rotated = RefreshToken(new_refresh)
                if str(rotated.get("sid") or "") != str(session.session_id):
                    raise AuthenticationFailed(
                        "Refreshed token is not bound to the current session."
                    )

                updated = UserSession.objects.filter(
                    pk=session.pk,
                    revoked_at__isnull=True,
                    credential_hash=incoming_hash,
                ).update(
                    credential_hash=hashlib.sha256(
                        str(new_refresh).encode("utf-8")
                    ).hexdigest(),
                    last_seen_at=timezone.now(),
                )
                if updated != 1:
                    raise AuthenticationFailed(
                        "Authentication session changed during token rotation."
                    )

            session.refresh_from_db()
            cache_session(session)
            return data
        except (InvalidToken, TokenError, AuthenticationFailed) as exc:
            if isinstance(exc, AuthenticationFailed):
                raise
            raise AuthenticationFailed(
                "Authentication session is invalid or revoked."
            ) from exc


class SessionTokenVerifySerializer(TokenVerifySerializer):
    """Make the token verification endpoint honor revocable server sessions."""

    def validate(self, attrs):
        data = super().validate(attrs)
        try:
            token = AccessToken(attrs["token"])
            session_id = token.get("sid")
            user_id = token.get("user_id")
            if session_id:
                if not user_id:
                    raise AuthenticationFailed(
                        "Authentication session is invalid or revoked."
                    )
                resolve_session(session_id, user_id=user_id)
        except (InvalidToken, TokenError, AuthenticationFailed) as exc:
            raise AuthenticationFailed(
                "Authentication session is invalid or revoked."
            ) from exc
        return data
