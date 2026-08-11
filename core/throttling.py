"""
Scoped throttling / rate-limiting helpers.

Scopes are hierarchical strings, e.g.:
  - "tickets:create:user:{id}"
  - "tickets:message:user:{id}"
  - "tickets:read:user:{id}"
  - "deploy:create:user:{id}"
  - "global:ip:{ip}"

Uses Django cache (Redis in production). Returns True if the request is ALLOWED.
"""
from __future__ import annotations

import hashlib
import logging
from functools import wraps
from typing import Callable, Optional

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle

logger = logging.getLogger("core.throttling")


def _key(scope: str) -> str:
    # Keep keys short but unique
    digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:40]
    return f"throttle:{digest}"


def check_scope(
    scope: str,
    limit: int,
    window_seconds: int,
    *,
    cost: int = 1,
) -> bool:
    """
    Token-bucket-ish fixed window counter.
    Returns True if under limit (allowed), False if throttled.
    """
    if limit is None or limit <= 0:
        return True
    if window_seconds <= 0:
        return True
    cache_key = _key(scope)
    current = cache.get(cache_key)
    if current is None:
        cache.set(cache_key, cost, timeout=window_seconds)
        return True
    try:
        current_int = int(current)
    except (TypeError, ValueError):
        cache.set(cache_key, cost, timeout=window_seconds)
        return True
    if current_int >= limit:
        return False
    try:
        # Prefer incr for atomicity when available
        if cost == 1:
            cache.incr(cache_key)
        else:
            cache.set(cache_key, current_int + cost, timeout=window_seconds)
    except ValueError:
        cache.set(cache_key, cost, timeout=window_seconds)
    return True


def remaining(scope: str, limit: int) -> int:
    if limit <= 0:
        return limit
    current = cache.get(_key(scope))
    try:
        used = int(current or 0)
    except (TypeError, ValueError):
        used = 0
    return max(0, limit - used)


def throttle_response(
    scope: str,
    limit: int,
    window_seconds: int,
    detail: str = "Rate limit exceeded. Please try again later.",
) -> Response:
    return Response(
        {
            "success": False,
            "message": detail,
            "error": "throttled",
            "scope": scope,
            "limit": limit,
            "window_seconds": window_seconds,
            "retry_after": window_seconds,
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(window_seconds)},
    )


def scoped_throttle(
    *,
    scope_builder: Callable,
    limit: int,
    window_seconds: int,
    detail: str = "Rate limit exceeded. Please try again later.",
):
    """
    Decorator for DRF APIView methods (sync or async).

    scope_builder(request, *args, **kwargs) -> str
    """

    def decorator(fn):
        if asyncio_iscoroutinefunction(fn):

            @wraps(fn)
            async def async_wrapper(self, request, *args, **kwargs):
                scope = scope_builder(request, *args, **kwargs)
                if not check_scope(scope, limit, window_seconds):
                    return throttle_response(scope, limit, window_seconds, detail)
                return await fn(self, request, *args, **kwargs)

            return async_wrapper

        @wraps(fn)
        def wrapper(self, request, *args, **kwargs):
            scope = scope_builder(request, *args, **kwargs)
            if not check_scope(scope, limit, window_seconds):
                return throttle_response(scope, limit, window_seconds, detail)
            return fn(self, request, *args, **kwargs)

        return wrapper

    return decorator


def asyncio_iscoroutinefunction(fn) -> bool:
    try:
        import asyncio
        return asyncio.iscoroutinefunction(fn)
    except Exception:
        return False


class ScopedRateThrottle(BaseThrottle):
    """
    DRF throttle class configurable per-view via:
      throttle_scope = "tickets.create"
      throttle_rate = "10/min"   # or "30/hour"
    """

    scope_attr = "throttle_scope"
    rate_attr = "throttle_rate"
    default_rate = "60/min"

    def allow_request(self, request, view) -> bool:
        scope_name = getattr(view, self.scope_attr, None) or "default"
        rate = getattr(view, self.rate_attr, None) or self.default_rate
        limit, window = self.parse_rate(rate)
        if limit is None:
            return True
        ident = self.get_ident(request)
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            ident = f"user:{user.pk}"
        else:
            ident = f"ip:{ident}"
        scope = f"{scope_name}:{ident}"
        self._scope = scope
        self._limit = limit
        self._window = window
        allowed = check_scope(scope, limit, window)
        if not allowed:
            self.wait = window  # type: ignore[attr-defined]
        return allowed

    def wait(self):  # noqa: A003 — DRF API
        return getattr(self, "_window", 60)

    @staticmethod
    def parse_rate(rate: str):
        if not rate:
            return None, 60
        try:
            num, period = rate.split("/")
            num = int(num)
            period = period.strip().lower()
            mapping = {
                "s": 1,
                "sec": 1,
                "second": 1,
                "seconds": 1,
                "m": 60,
                "min": 60,
                "minute": 60,
                "minutes": 60,
                "h": 3600,
                "hour": 3600,
                "hours": 3600,
                "d": 86400,
                "day": 86400,
                "days": 86400,
            }
            # allow "10/min" or "10/minute"
            unit = period
            for key, seconds in mapping.items():
                if period.startswith(key):
                    return num, seconds
            return num, 60
        except Exception:
            return None, 60


# Convenience builders
def user_scope(prefix: str):
    def builder(request, *args, **kwargs) -> str:
        uid = getattr(getattr(request, "user", None), "pk", None) or "anon"
        return f"{prefix}:user:{uid}"

    return builder


def ip_scope(prefix: str):
    def builder(request, *args, **kwargs) -> str:
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        if not ip:
            ip = request.META.get("REMOTE_ADDR", "0.0.0.0")
        return f"{prefix}:ip:{ip}"

    return builder
