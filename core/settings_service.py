"""
Read/write SystemSetting with process cache + Django cache.
Fallback chain: DB → code defaults (initial_config.DEFAULTS) → hardcoded.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "syssetting:"
_CACHE_ALL = "syssetting:__all__"
_CACHE_TTL = 60  # seconds


def _defaults_map() -> dict[str, Any]:
    try:
        from core.initial_config import DEFAULTS

        return {d["key"]: d for d in DEFAULTS}
    except Exception:
        return {}


def get_setting(key: str, default: Any = None) -> Any:
    """
    Return cast value for key.
    """
    cache_key = f"{_CACHE_PREFIX}{key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from core.models import SystemSetting

        row = SystemSetting.objects.filter(key=key).first()
        if row is not None:
            val = row.cast_value()
            cache.set(cache_key, val, _CACHE_TTL)
            return val
    except (OperationalError, ProgrammingError, ImportError) as exc:
        # Migrations not applied / app not ready
        logger.debug("get_setting(%s) DB unavailable: %s", key, exc)

    # Code defaults
    meta = _defaults_map().get(key)
    if meta is not None:
        val = meta.get("default")
        # Cast via a transient type if needed
        return val if default is None else (val if val is not None else default)

    return default


def get_str(key: str, default: str = "") -> str:
    v = get_setting(key, default)
    return default if v is None else str(v)


def get_int(key: str, default: int = 0) -> int:
    v = get_setting(key, default)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def get_float(key: str, default: float = 0.0) -> float:
    v = get_setting(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def get_bool(key: str, default: bool = False) -> bool:
    v = get_setting(key, default)
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def get_json(key: str, default: Any = None) -> Any:
    v = get_setting(key, default)
    return default if v is None else v


def set_setting(key: str, value: Any, *, actor: str | None = None) -> bool:
    """Update an editable setting. Returns True on success."""
    try:
        from core.models import SystemSetting

        row = SystemSetting.objects.filter(key=key).first()
        if row is None:
            return False
        if not row.is_editable:
            return False
        row.set_cast_value(value)
        row.save(update_fields=["value", "updated_at"])
        cache.delete(f"{_CACHE_PREFIX}{key}")
        cache.delete(_CACHE_ALL)
        logger.info("SystemSetting %s updated (by %s)", key, actor or "system")
        return True
    except Exception:
        logger.exception("Failed to set setting %s", key)
        return False


def all_settings(*, include_secrets: bool = False) -> list[dict]:
    try:
        from core.models import SystemSetting

        rows = SystemSetting.objects.all().order_by("category", "key")
        out = []
        for r in rows:
            item = {
                "key": r.key,
                "value": "***" if (r.is_secret and not include_secrets) else r.cast_value(),
                "raw_value": "***" if (r.is_secret and not include_secrets) else r.value,
                "value_type": r.value_type,
                "category": r.category,
                "label": r.label or r.key,
                "description": r.description,
                "is_secret": r.is_secret,
                "is_editable": r.is_editable,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            out.append(item)
        return out
    except (OperationalError, ProgrammingError):
        return []


# ---- Convenience domain helpers used by deployment pipeline ----

def mirror_docker() -> str:
    return get_str("mirror.docker", "docker.io")


def mirror_python() -> str:
    return get_str("mirror.python", "https://pypi.org/simple")


def mirror_npm() -> str:
    return get_str("mirror.npm", "https://registry.npmjs.org")


def mirror_apt() -> str:
    return get_str("mirror.apt", "")


def mirror_composer() -> str:
    """Return the Composer (PHP) package mirror.

    Used by the Laravel/PHP Dockerfile templates to redirect packagist to a
    local mirror via ``composer config -g repo.packagist composer <mirror>``.
    Empty string means "use the public packagist.org" — the template has
    ``if [ -n "{MIRROR_COMPOSER}" ]`` guards so an empty value disables the
    redirect cleanly.
    """
    return get_str("mirror.composer", "")


def mirror_go() -> str:
    """Return the GOPROXY string for Go module downloads (empty = default)."""
    return get_str("mirror.go", "")


def build_resource_mode() -> str:
    return get_str("build.resource_mode", "static").strip().lower()


def build_max_cpu() -> float:
    return get_float("build.max_cpu", 1.0)


def build_max_ram_mb() -> int:
    return get_int("build.max_ram_mb", 1024)


def build_parallelism() -> int:
    return max(1, get_int("build.parallelism", 1))


def build_max_wait_minute() -> int:
    return max(1, get_int("build.max_wait_minute", 5))


def max_deploy_time_minute() -> int:
    return get_int("deploy.max_time_minute", 10)


def default_runtime_versions() -> dict:
    return get_json("runtime.versions", {}) or {}


def default_ports_map() -> dict:
    return get_json("ports.defaults", {}) or {}


def default_expose_port() -> int:
    return get_int("ports.default_expose", 80)


def default_spa_build_dir() -> str:
    return get_str("deploy.spa_build_dir", "dist")


def default_worker_count() -> int:
    return get_int("deploy.worker_count", 1)


def dockerfile_template(platform: str) -> Optional[str]:
    key = f"dockerfile.{platform}"
    val = get_str(key, "")
    return val or None
