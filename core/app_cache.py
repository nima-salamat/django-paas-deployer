"""Shared Redis JSON cache helpers for services / plans / tickets / users.

Uses django-redis (CACHES['default']). Soft-fail: cache errors never break APIs.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Optional

from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder

logger = logging.getLogger("core.app_cache")

# TTLs (seconds)
SERVICE_USER_TTL = 3600          # 1 hour
SERVICE_ADMIN_TTL = 3600
PLAN_TTL = 86400                 # 24 hours
TICKET_USER_TTL = 3600
TICKET_ADMIN_TTL = 3600
USER_ADMIN_TTL = 3600

# Limits
SERVICE_USER_LIMIT = 50
SERVICE_ADMIN_LIMIT = 100
TICKET_USER_LIMIT = 50
TICKET_ADMIN_LIMIT = 100
USER_ADMIN_LIMIT = 100


def _dumps(obj: Any) -> str:
    return json.dumps(obj, cls=DjangoJSONEncoder, separators=(",", ":"), ensure_ascii=False)


def _loads(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except Exception:
        return None


def cache_get(key: str) -> Any:
    try:
        return _loads(cache.get(key))
    except Exception:
        logger.exception("cache_get failed key=%s", key)
        return None


def cache_set(key: str, value: Any, ttl: int) -> bool:
    try:
        cache.set(key, _dumps(value) if not isinstance(value, str) else value, timeout=ttl)
        return True
    except Exception:
        logger.exception("cache_set failed key=%s", key)
        return False


def cache_delete(*keys: str) -> None:
    try:
        if keys:
            cache.delete_many(list(keys))
    except Exception:
        logger.exception("cache_delete failed")


def cache_delete_pattern(pattern: str) -> None:
    """Best-effort delete by pattern (django-redis delete_pattern)."""
    try:
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern(pattern)
        else:
            # Fallback: try raw redis client
            from django_redis import get_redis_connection
            r = get_redis_connection("default")
            for key in r.scan_iter(match=pattern, count=200):
                r.delete(key)
    except Exception:
        logger.exception("cache_delete_pattern failed pattern=%s", pattern)


def make_query_key(prefix: str, user_id: Any, params: dict) -> str:
    """Stable key for filtered list queries."""
    items = sorted((str(k), str(v)) for k, v in (params or {}).items() if v not in (None, ""))
    raw = "&".join(f"{k}={v}" for k, v in items)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:u:{user_id}:q:{digest}"


# ----- Services -----
def service_user_list_key(user_id: int, params: dict | None = None) -> str:
    return make_query_key("svc:user", user_id, params or {})


def service_user_detail_key(user_id: int, service_id: str) -> str:
    return f"svc:user:{user_id}:id:{service_id}"


def service_admin_list_key(params: dict | None = None) -> str:
    return make_query_key("svc:admin", "all", params or {})


def invalidate_user_services(user_id: int) -> None:
    cache_delete_pattern(f"svc:user:{user_id}:*")
    cache_delete_pattern("svc:admin:*")


def invalidate_all_services() -> None:
    cache_delete_pattern("svc:user:*")
    cache_delete_pattern("svc:admin:*")


# ----- Plans -----
def plan_list_key(params: dict | None = None) -> str:
    return make_query_key("plan:pub", "all", params or {})


def plan_admin_list_key(params: dict | None = None) -> str:
    return make_query_key("plan:admin", "all", params or {})


def plan_detail_key(plan_id: str) -> str:
    return f"plan:id:{plan_id}"


def invalidate_all_plans() -> None:
    cache_delete_pattern("plan:*")


# ----- Tickets -----
def ticket_user_list_key(user_id: int, params: dict | None = None) -> str:
    return make_query_key("tkt:user", user_id, params or {})


def ticket_admin_list_key(params: dict | None = None) -> str:
    return make_query_key("tkt:admin", "all", params or {})


def invalidate_user_tickets(user_id: int) -> None:
    cache_delete_pattern(f"tkt:user:{user_id}:*")
    cache_delete_pattern("tkt:admin:*")


def invalidate_all_tickets() -> None:
    cache_delete_pattern("tkt:user:*")
    cache_delete_pattern("tkt:admin:*")


# ----- Users (admin) -----
def user_admin_list_key(params: dict | None = None) -> str:
    return make_query_key("usr:admin", "all", params or {})


def invalidate_all_users_admin() -> None:
    cache_delete_pattern("usr:admin:*")



def scan_app_cache_keys(prefix: str = "", limit: int = 100) -> list:
    """List app-cache related keys for admin UI (svc:, plan:, tkt:, usr:)."""
    out = []
    try:
        from django_redis import get_redis_connection
        r = get_redis_connection("default")
        patterns = [f"{prefix}*"] if prefix else ["svc:*", "plan:*", "tkt:*", "usr:*"]
        seen = set()
        for pat in patterns:
            for key in r.scan_iter(match=pat, count=200):
                k = key.decode() if isinstance(key, bytes) else str(key)
                # django-redis may prefix keys; show as stored
                if k in seen:
                    continue
                seen.add(k)
                try:
                    ktype = r.type(key)
                    if isinstance(ktype, bytes):
                        ktype = ktype.decode()
                    ttl = r.ttl(key)
                except Exception:
                    ktype, ttl = "?", -1
                out.append({"key": k, "type": ktype, "ttl": ttl})
                if len(out) >= limit:
                    return out
    except Exception:
        logger.exception("scan_app_cache_keys failed")
    return out


def get_app_cache_overview() -> dict:
    """Counts of keys per namespace for admin dashboard."""
    overview = {
        "redis_ok": False,
        "svc": 0,
        "plan": 0,
        "tkt": 0,
        "usr": 0,
        "msgcache": 0,
        "memory": {},
    }
    try:
        from django_redis import get_redis_connection
        r = get_redis_connection("default")
        overview["redis_ok"] = bool(r.ping())
        for ns, field in (("svc:", "svc"), ("plan:", "plan"), ("tkt:", "tkt"), ("usr:", "usr"), ("msgcache:", "msgcache")):
            n = 0
            for _ in r.scan_iter(match=f"{ns}*", count=200):
                n += 1
                if n >= 5000:
                    break
            overview[field] = n
        try:
            info = r.info(section="memory")
            overview["memory"] = {
                "used_memory_human": info.get("used_memory_human"),
                "maxmemory_human": info.get("maxmemory_human"),
            }
        except Exception:
            pass
    except Exception:
        logger.exception("get_app_cache_overview failed")
    return overview


def invalidate_namespace(ns: str) -> None:
    """ns in svc, plan, tkt, usr, all."""
    if ns == "all":
        cache_delete_pattern("svc:*")
        cache_delete_pattern("plan:*")
        cache_delete_pattern("tkt:*")
        cache_delete_pattern("usr:*")
        return
    mapping = {
        "svc": "svc:*",
        "plan": "plan:*",
        "tkt": "tkt:*",
        "usr": "usr:*",
    }
    pat = mapping.get(ns)
    if pat:
        cache_delete_pattern(pat)
