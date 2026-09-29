"""Shared server-side session authority for HTTP and realtime adapters."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
import json
import logging
from collections.abc import Iterable

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from .models import Device, UserSession

logger = logging.getLogger("auth_users.session")

SESSION_CACHE_PREFIX = "auth:session:"
SESSION_CACHE_VERSION = 3
DEFAULT_SESSION_CACHE_TTL = 15 * 60
DEFAULT_SESSION_DB_TOUCH_INTERVAL = 5 * 60


@dataclass(frozen=True)
class AuthenticatedSessionContext:
    session_id: str
    user_id: int
    device_id: str
    auth_generation: int
    expires_at: datetime


@dataclass(frozen=True)
class _CachedSession:
    context: AuthenticatedSessionContext


def session_cache_key(session_id: str) -> str:
    return f"{SESSION_CACHE_PREFIX}{session_id}"


def _cache_ttl() -> int:
    try:
        return max(60, int(getattr(settings, "AUTH_SESSION_CACHE_TTL", DEFAULT_SESSION_CACHE_TTL)))
    except (TypeError, ValueError):
        return DEFAULT_SESSION_CACHE_TTL


def _db_touch_interval() -> int:
    try:
        return max(
            0,
            int(
                getattr(
                    settings,
                    "AUTH_SESSION_DB_TOUCH_INTERVAL",
                    DEFAULT_SESSION_DB_TOUCH_INTERVAL,
                )
            ),
        )
    except (TypeError, ValueError):
        return DEFAULT_SESSION_DB_TOUCH_INTERVAL


def _serialize_cache_value(
    context: AuthenticatedSessionContext,
) -> str:
    return json.dumps(
        {
            "version": SESSION_CACHE_VERSION,
            "session": {
                "session_id": context.session_id,
                "user_id": context.user_id,
                "device_id": context.device_id,
                "auth_generation": context.auth_generation,
                "expires_at": context.expires_at.isoformat(),
            },
        },
        separators=(",", ":"),
    )


def _deserialize_cache_value(value) -> _CachedSession | None:
    if not value:
        return None
    try:
        data = json.loads(value) if isinstance(value, str) else value

        # Accept the pre-v2 cache shape during rolling deployments. Those
        # values do not carry a lease timestamp, so treat them as freshly read.
        if "session" in data:
            session_data = data["session"]
        else:
            session_data = data

        expires_at = datetime.fromisoformat(str(session_data["expires_at"]))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=dt_timezone.utc)

        return _CachedSession(
            context=AuthenticatedSessionContext(
                session_id=str(session_data["session_id"]),
                user_id=int(session_data["user_id"]),
                device_id=str(session_data["device_id"]),
                auth_generation=int(session_data["auth_generation"]),
                expires_at=expires_at,
            ),
            cached_at=cached_at,
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


def _delete_session_cache_keys(session_ids: Iterable[str]) -> None:
    ids = tuple(dict.fromkeys(str(value) for value in session_ids if value))
    if not ids:
        return
    try:
        cache.delete_many([session_cache_key(session_id) for session_id in ids])
    except Exception:
        logger.warning(
            "session cache invalidation failed sessions=%s",
            ",".join(session_id[:12] for session_id in ids[:10]),
            exc_info=True,
        )


def schedule_session_cache_invalidation(session_ids: Iterable[str]) -> None:
    """Invalidate positive session cache entries after the current transaction commits."""
    ids = tuple(dict.fromkeys(str(value) for value in session_ids if value))
    if not ids:
        return
    transaction.on_commit(lambda: _delete_session_cache_keys(ids))


def _write_cached_context(
    context: AuthenticatedSessionContext,
    *,
    now: datetime,
) -> None:
    remaining = int((context.expires_at - now).total_seconds())
    ttl = min(_cache_ttl(), remaining)
    if ttl <= 0:
        return
    try:
        cache.set(
            session_cache_key(context.session_id),
            _serialize_cache_value(context),
            ttl,
        )
    except Exception:
        logger.warning(
            "session cache write failed session=%s",
            context.session_id[:12],
            exc_info=True,
        )


def _touch_session_cache(
    context: AuthenticatedSessionContext,
    *,
    now: datetime,
) -> bool:
    remaining = int((context.expires_at - now).total_seconds())
    ttl = min(_cache_ttl(), remaining)
    if ttl <= 0:
        return False
    try:
        return bool(cache.touch(session_cache_key(context.session_id), ttl))
    except Exception:
        logger.warning(
            "session cache touch failed session=%s",
            context.session_id[:12],
            exc_info=True,
        )
        return False


def cache_session(
    session: UserSession,
    *,
    now: datetime | None = None,
) -> AuthenticatedSessionContext:
    """Cache one active session for a bounded sliding Redis lease."""
    now = now or timezone.now()
    context = _context_from_session(session)
    _write_cached_context(context, now=now)
    return context


def get_active_session_for_update(
    session_id: str,
    *,
    user_id=None,
) -> UserSession:
    """Load and lock the authoritative active session for atomic security changes."""
    if not session_id:
        raise AuthenticationFailed("Authentication session is missing.")

    now = timezone.now()
    query = UserSession.objects.select_for_update().select_related("device").filter(
        session_id=str(session_id),
        revoked_at__isnull=True,
        expires_at__gt=now,
        device__revoked_at__isnull=True,
    )
    if user_id is not None:
        query = query.filter(user_id=user_id)

    session = query.first()
    if session is None:
        raise AuthenticationFailed("Authentication session is invalid or revoked.")
    return session


def resolve_session(session_id: str, *, user_id=None) -> AuthenticatedSessionContext:
    """Resolve an active session, using Redis as a bounded acceleration layer."""
    if not session_id:
        raise AuthenticationFailed("Authentication session is missing.")

    now = timezone.now()
    key = session_cache_key(str(session_id))

    try:
        cached_entry = _deserialize_cache_value(cache.get(key))
    except Exception:
        cached_entry = None
        logger.warning(
            "session cache read failed; using database session=%s",
            str(session_id)[:12],
            exc_info=True,
        )

    if cached_entry is not None:
        cached = cached_entry.context
        same_user = user_id is None or cached.user_id == int(user_id)
        if same_user and cached.expires_at > now:
            # touch() extends an existing key without recreating it. If a
            # concurrent revoke deleted the key between GET and TOUCH, fall
            # through to the authoritative database lookup.
            if _touch_session_cache(cached, now=now):
                return cached

        try:
            cache.delete(key)
        except Exception:
            logger.debug("failed to delete stale session cache key=%s", key, exc_info=True)

    query = UserSession.objects.select_related("device").filter(
        session_id=str(session_id),
        revoked_at__isnull=True,
        expires_at__gt=now,
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

    touch_interval = _db_touch_interval()
    if (
        session.last_seen_at is None
        or touch_interval == 0
        or (now - session.last_seen_at).total_seconds() >= touch_interval
    ):
        UserSession.objects.filter(pk=session.pk).update(last_seen_at=now)

    return cache_session(session, now=now)


def revoke_session_ids(session_ids: Iterable[str]) -> int:
    """Revoke sessions atomically and invalidate their cache entries after commit."""
    ids = tuple(dict.fromkeys(str(value) for value in session_ids if value))
    if not ids:
        return 0

    now = timezone.now()
    with transaction.atomic():
        count = UserSession.objects.filter(
            session_id__in=ids,
            revoked_at__isnull=True,
        ).update(revoked_at=now)
        schedule_session_cache_invalidation(ids)
    return count


def revoke_session_queryset(queryset) -> int:
    """Revoke an admin-selected session queryset through the canonical security path."""
    with transaction.atomic():
        rows = list(
            queryset.filter(revoked_at__isnull=True).values_list("session_id", flat=True)
        )
        if not rows:
            return 0
        count = UserSession.objects.filter(
            session_id__in=rows,
            revoked_at__isnull=True,
        ).update(revoked_at=timezone.now())
        schedule_session_cache_invalidation(rows)
    return count


def invalidate_session(session_id: str) -> bool:
    """Revoke one session and invalidate its positive cache entry after commit."""
    with transaction.atomic():
        session = UserSession.objects.select_for_update().filter(
            session_id=str(session_id)
        ).first()
        if session is None:
            return False
        changed = session.revoked_at is None
        if changed:
            session.revoked_at = timezone.now()
            session.save(update_fields=["revoked_at"])
            schedule_session_cache_invalidation([session.session_id])
        return changed


def invalidate_device(device_id, *, user_id=None) -> int:
    """Revoke a device and all of its active sessions atomically."""
    with transaction.atomic():
        device_query = Device.objects.select_for_update().filter(public_id=device_id)
        if user_id is not None:
            device_query = device_query.filter(user_id=user_id)
        device = device_query.first()
        if device is None:
            return 0

        ids = list(
            UserSession.objects.filter(
                device=device,
                revoked_at__isnull=True,
            ).values_list("session_id", flat=True)
        )
        count = UserSession.objects.filter(
            session_id__in=ids,
            revoked_at__isnull=True,
        ).update(revoked_at=timezone.now())

        if device.revoked_at is None:
            device.revoked_at = timezone.now()
            device.save(update_fields=["revoked_at"])

        schedule_session_cache_invalidation(ids)
    return count


def invalidate_all_sessions(user_id: int) -> int:
    """Revoke every active session owned by a user."""
    with transaction.atomic():
        ids = list(
            UserSession.objects.filter(
                user_id=user_id,
                revoked_at__isnull=True,
            ).values_list("session_id", flat=True)
        )
        if not ids:
            return 0
        count = UserSession.objects.filter(
            session_id__in=ids,
            revoked_at__isnull=True,
        ).update(revoked_at=timezone.now())
        schedule_session_cache_invalidation(ids)
    return count
