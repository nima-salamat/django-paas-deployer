"""Session-aware SimpleJWT serializers used during the migration window."""
from __future__ import annotations

import hashlib

from django.utils import timezone
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken, TokenError

from .models import UserSession
from .session_auth import resolve_session


class SessionTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        raw_refresh = attrs.get("refresh")
        try:
            refresh = RefreshToken(raw_refresh)
            session_id = refresh.get("sid")
            user_id = refresh.get("user_id")
            if session_id:
                resolve_session(session_id, user_id=user_id)
        except (InvalidToken, TokenError, AuthenticationFailed) as exc:
            raise AuthenticationFailed("Authentication session is invalid or revoked.") from exc

        data = super().validate(attrs)
        if session_id and data.get("refresh"):
            UserSession.objects.filter(
                session_id=str(session_id), revoked_at__isnull=True
            ).update(
                credential_hash=hashlib.sha256(data["refresh"].encode("utf-8")).hexdigest(),
                last_seen_at=timezone.now(),
            )
        return data
