"""Shared server-side session authority for HTTP and realtime adapters."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
import json
import logging

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from .models import Device, UserSession

logger = logging.getLogger("auth_users.session")
SESSION_CACHE_PREFIX = "auth:session:"


@dataclass(frozen=True)
class AuthenticatedSessionContext:
    session_id: str
    user_id: int
    device_id: str
    auth_generation: int
    expires_at: datetime


def session_cache_key(session_id: str) -> str:
    return f"{SESSION_CACHE_PREFIX}{session_id}"


def _serialize(context: AuthenticatedSessionContext) -> str:
    return json.dumps(
        {
            "session_id": context.session_id,
            "user_id": context.user_id,
            "device_id": context.device_id,
            "auth_generation": context.auth_generation,
            "expires_at": context.expires_at.isoformat(),
        },
        separators=(",", ":"),
    )


def _deserialize(value):
    if not value:
        return None
    try:
        data = json.loads(value) if isinstance(value, str) else value
        expires_at = datetime.fromisoformat(str(data["expires_at"]))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=dt_timezone.utc)
        return AuthenticatedSessionContext(
            session_id=str(data["session_id"]),
            user_id=int(data["user_id"]),
            device_id=str(data["device_id"]),
            auth_generation=int(data["auth_generation"]),
            expires_at=expires_at,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _context_from_session(session: UserSession) -> AuthenticatedSessionContext:
    return AuthenticatedSessionContext(
        session_id=session.session_id,
        user_id=session.user_id,
        device_id=str(session.device.public_id),
        auth_generation=session.auth_generation,
        expires_at=session.expires_at,
    )


def cache_session(session: UserSession) -> AuthenticatedSessionContext:
    context = _context_from_session(session)
    ttl = max(1, int((session.expires_at - timezone.now()).total_seconds()))
    try:
        cache.set(session_cache_key(session.session_id), _serialize(context), ttl)
    except Exception:
        logger.warning("session cache write failed session=%s", session.session_id[:12], exc_info=True)
    return context


def resolve_session(session_id: str, *, user_id=None) -> AuthenticatedSessionContext:
    """Resolve an active session, using Redis only as an acceleration layer."""
    if not session_id:
        raise AuthenticationFailed("Authentication session is missing.")

    key = session_cache_key(str(session_id))
    try:
        cached = _deserialize(cache.get(key))
    except Exception:
        cached = None
        logger.warning("session cache read failed; using database", exc_info=True)
    if cached and cached.expires_at > timezone.now() and (
        user_id is None or cached.user_id == int(user_id)
    ):
        return cached

    query = UserSession.objects.select_related("device").filter(
        session_id=str(session_id),
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
        device__revoked_at__isnull=True,
    )
    if user_id is not None:
        query = query.filter(user_id=user_id)
    session = query.first()
    if session is None:
        try:
            cache.delete(key)
        except Exception:
            pass
        raise AuthenticationFailed("Authentication session is invalid or revoked.")

    UserSession.objects.filter(pk=session.pk).update(last_seen_at=timezone.now())
    return cache_session(session)


def invalidate_session(session_id: str) -> bool:
    """Revoke a session and invalidate its positive cache entry."""
    with transaction.atomic():
        session = UserSession.objects.select_for_update().filter(session_id=str(session_id)).first()
        if session is None:
            return False
        if session.revoked_at is None:
            session.revoked_at = timezone.now()
            session.save(update_fields=["revoked_at"])
    try:
        cache.delete(session_cache_key(str(session_id)))
    except Exception:
        logger.warning("session cache invalidation failed session=%s", str(session_id)[:12], exc_info=True)
    return True


def invalidate_device(device_id, *, user_id=None) -> int:
    query = UserSession.objects.filter(device__public_id=device_id, revoked_at__isnull=True)
    if user_id is not None:
        query = query.filter(user_id=user_id)
    ids = list(query.values_list("session_id", flat=True))
    with transaction.atomic():
        count = query.update(revoked_at=timezone.now())
    for session_id in ids:
        try:
            cache.delete(session_cache_key(session_id))
        except Exception:
            logger.warning("device session cache invalidation failed", exc_info=True)
    Device.objects.filter(public_id=device_id, **({"user_id": user_id} if user_id else {})).update(
        revoked_at=timezone.now()
    )
    return count


def invalidate_all_sessions(user_id: int) -> int:
    ids = list(
        UserSession.objects.filter(user_id=user_id, revoked_at__isnull=True)
        .values_list("session_id", flat=True)
    )
    count = UserSession.objects.filter(
        user_id=user_id, revoked_at__isnull=True
    ).update(revoked_at=timezone.now())
    for session_id in ids:
        try:
            cache.delete(session_cache_key(session_id))
        except Exception:
            logger.warning("all-session cache invalidation failed", exc_info=True)
    return count
