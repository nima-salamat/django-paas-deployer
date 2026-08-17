"""Shared Redis JSON cache helpers for services / plans / tickets / users.

Uses the raw redis client (same as messenger.message_cache).
Soft-fail: cache errors never break APIs.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder

logger = logging.getLogger("core.app_cache")

SERVICE_USER_TTL = 3600
SERVICE_ADMIN_TTL = 3600
PLAN_TTL = 86400
TICKET_USER_TTL = 3600
TICKET_ADMIN_TTL = 3600
USER_ADMIN_TTL = 3600

SERVICE_USER_LIMIT = 50
SERVICE_ADMIN_LIMIT = 100
TICKET_USER_LIMIT = 50
TICKET_ADMIN_LIMIT = 100
USER_ADMIN_LIMIT = 100


def _redis():
    try:
        from django_redis import get_redis_connection
        return get_redis_connection("default")
    except Exception:
        logger.exception("app_cache: cannot obtain redis connection")
        return None


def _dumps(obj: Any) -> str:
    return json.dumps(obj, cls=DjangoJSONEncoder, separators=(",", ":"), ensure_ascii=False)


def _loads(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def cache_get(key: str) -> Any:
    r = _redis()
    if not r:
        return None
    try:
        return _loads(r.get(key))
    except Exception:
        logger.exception("cache_get failed key=%s", key)
        return None


def cache_set(key: str, value: Any, ttl: int) -> bool:
    r = _redis()
    if not r:
        return False
    try:
        payload = value if isinstance(value, str) else _dumps(value)
        if ttl and ttl > 0:
            r.setex(key, int(ttl), payload)
        else:
            r.set(key, payload)
        return True
    except Exception:
        logger.exception("cache_set failed key=%s", key)
        return False


def cache_delete(*keys: str) -> None:
    r = _redis()
    if not r or not keys:
        return
    try:
        r.delete(*keys)
    except Exception:
        logger.exception("cache_delete failed")


def cache_delete_pattern(pattern: str) -> None:
    r = _redis()
    if not r:
        return
    try:
        patterns = [pattern]
        if not pattern.startswith(":"):
            patterns.append(f":1:{pattern}")
            patterns.append(f"*:{pattern}")
        pipe = r.pipeline(transaction=False)
        n = 0
        for pat in patterns:
            for key in r.scan_iter(match=pat, count=200):
                pipe.delete(key)
                n += 1
                if n >= 5000:
                    break
            if n >= 5000:
                break
        if n:
            pipe.execute()
    except Exception:
        logger.exception("cache_delete_pattern failed pattern=%s", pattern)


def make_query_key(prefix: str, user_id: Any, params: dict) -> str:
    items = sorted((str(k), str(v)) for k, v in (params or {}).items() if v not in (None, ""))
    raw = "&".join(f"{k}={v}" for k, v in items)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:u:{user_id}:q:{digest}"


def service_user_list_key(user_id: int, params: dict | None = None) -> str:
    return make_query_key("svc:user", user_id, params or {})


def service_user_detail_key(user_id: int, service_id: str) -> str:
    # Align with list keys from make_query_key (prefix:u:{user_id}:...)
    return f"svc:user:u:{user_id}:id:{service_id}"


def service_admin_list_key(params: dict | None = None) -> str:
    return make_query_key("svc:admin", "all", params or {})


def invalidate_user_services(user_id: int) -> None:
    # List keys: svc:user:u:{user_id}:q:{digest}
    # Detail keys: svc:user:u:{user_id}:id:{service_id}
    # Also clear any legacy keys that used svc:user:{user_id}:...
    cache_delete_pattern(f"svc:user:u:{user_id}:*")
    cache_delete_pattern(f"svc:user:{user_id}:*")
    cache_delete_pattern("svc:admin:*")


def invalidate_all_services() -> None:
    cache_delete_pattern("svc:user:*")
    cache_delete_pattern("svc:admin:*")


def plan_list_key(params: dict | None = None) -> str:
    return make_query_key("plan:pub", "all", params or {})


def plan_admin_list_key(params: dict | None = None) -> str:
    return make_query_key("plan:admin", "all", params or {})


def plan_detail_key(plan_id: str) -> str:
    return f"plan:id:{plan_id}"


def invalidate_all_plans() -> None:
    cache_delete_pattern("plan:*")


def ticket_user_list_key(user_id: int, params: dict | None = None) -> str:
    return make_query_key("tkt:user", user_id, params or {})


def ticket_admin_list_key(params: dict | None = None) -> str:
    return make_query_key("tkt:admin", "all", params or {})


def invalidate_user_tickets(user_id: int) -> None:
    # List keys: tkt:user:u:{user_id}:q:{digest}
    # Also clear any legacy keys that used tkt:user:{user_id}:...
    cache_delete_pattern(f"tkt:user:u:{user_id}:*")
    cache_delete_pattern(f"tkt:user:{user_id}:*")
    cache_delete_pattern("tkt:admin:*")


def invalidate_all_tickets() -> None:
    cache_delete_pattern("tkt:user:*")
    cache_delete_pattern("tkt:admin:*")


def user_admin_list_key(params: dict | None = None) -> str:
    return make_query_key("usr:admin", "all", params or {})


def invalidate_all_users_admin() -> None:
    cache_delete_pattern("usr:admin:*")


def scan_app_cache_keys(prefix: str = "", limit: int = 100) -> list:
    out = []
    r = _redis()
    if not r:
        return out
    try:
        patterns = [f"{prefix}*", f":1:{prefix}*"] if prefix else [
            "svc:*", "plan:*", "tkt:*", "usr:*",
            ":1:svc:*", ":1:plan:*", ":1:tkt:*", ":1:usr:*",
        ]
        seen = set()
        for pat in patterns:
            for key in r.scan_iter(match=pat, count=200):
                k = key.decode() if isinstance(key, bytes) else str(key)
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
    overview = {"redis_ok": False, "svc": 0, "plan": 0, "tkt": 0, "usr": 0, "msgcache": 0, "memory": {}}
    r = _redis()
    if not r:
        return overview
    try:
        overview["redis_ok"] = bool(r.ping())
        for ns, field in (("svc:", "svc"), ("plan:", "plan"), ("tkt:", "tkt"), ("usr:", "usr"), ("msgcache:", "msgcache")):
            n = 0
            for pat in (f"{ns}*", f":1:{ns}*"):
                for _ in r.scan_iter(match=pat, count=200):
                    n += 1
                    if n >= 5000:
                        break
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
    if ns == "all":
        for p in ("svc:*", "plan:*", "tkt:*", "usr:*"):
            cache_delete_pattern(p)
        return
    mapping = {"svc": "svc:*", "plan": "plan:*", "tkt": "tkt:*", "usr": "usr:*"}
    pat = mapping.get(ns)
    if pat:
        cache_delete_pattern(pat)


def get_cache_key_preview(key: str, max_len: int = 400) -> dict:
    """Return type, ttl and truncated value for a single key."""
    r = _redis()
    out = {"key": key, "type": "?", "ttl": -2, "value": None, "exists": False}
    if not r:
        return out
    try:
        ktype = r.type(key)
        if isinstance(ktype, bytes):
            ktype = ktype.decode()
        out["type"] = ktype
        out["ttl"] = r.ttl(key)
        if ktype == "none":
            return out
        out["exists"] = True
        raw = r.get(key) if ktype == "string" else None
        if raw is not None:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            if len(raw) > max_len:
                out["value"] = raw[:max_len] + "…"
            else:
                out["value"] = raw
        else:
            out["value"] = f"<{ktype} value not previewed>"
    except Exception:
        logger.exception("get_cache_key_preview failed key=%s", key)
    return out


def delete_cache_keys(*keys: str) -> int:
    r = _redis()
    if not r or not keys:
        return 0
    try:
        return int(r.delete(*keys) or 0)
    except Exception:
        logger.exception("delete_cache_keys failed")
        return 0
