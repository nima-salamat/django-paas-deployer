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
    return str(_wagtail_core_value("mirror_docker", get_str("mirror.docker", "docker.io")) or "docker.io")


def mirror_python() -> str:
    return str(_wagtail_core_value("mirror_python", get_str("mirror.python", "https://pypi.org/simple")) or "https://pypi.org/simple")


def mirror_npm() -> str:
    fallback = "https://registry.npmjs.org"
    try:
        from core.global_settings.config import MIRROR_NPM
        fallback = (MIRROR_NPM or "").strip() or fallback
    except Exception:
        pass
    return str(_wagtail_core_value("mirror_npm", get_str("mirror.npm", fallback)) or fallback)


def mirror_apt() -> str:
    return str(_wagtail_core_value("mirror_apt", get_str("mirror.apt", "")) or "")


def mirror_composer() -> str:
    """Return the Composer (PHP) package mirror.

    Used by the Laravel/PHP Dockerfile templates to redirect packagist to a
    local mirror via ``composer config -g repo.packagist composer <mirror>``.
    Empty string means "use the public packagist.org" — the template has
    ``if [ -n "{MIRROR_COMPOSER}" ]`` guards so an empty value disables the
    redirect cleanly.
    """
    return str(_wagtail_core_value("mirror_composer", get_str("mirror.composer", "")) or "")


def mirror_go() -> str:
    """Return the GOPROXY string for Go module downloads (empty = default)."""
    return str(_wagtail_core_value("mirror_go", get_str("mirror.go", "")) or "")


def build_resource_mode() -> str:
    return str(_wagtail_core_value("build_resource_mode", get_str("build.resource_mode", "static")) or "static").strip().lower()




def _wagtail_core_value(field: str, default: Any) -> Any:
    """Read operator settings from the unified Wagtail CoreSettings page."""
    try:
        from core.models import CoreSettings
        obj = CoreSettings.load()
        value = getattr(obj, field, None)
        return default if value is None else value
    except Exception:
        return default


def build_pids_limit() -> int:
    return max(128, min(int(_wagtail_core_value("build_pids_limit", get_int("deploy.build_pids_limit", 2048))), 8192))


def build_shm_mb() -> int:
    return max(16, min(int(_wagtail_core_value("build_shm_mb", get_int("deploy.build_shm_mb", 64))), 512))


def build_max_cpu() -> float:
    return max(0.25, min(float(_wagtail_core_value("build_max_cpu", get_float("build.max_cpu", 1.0))), 8.0))


def build_max_ram_mb() -> int:
    return max(256, min(int(_wagtail_core_value("build_max_ram_mb", get_int("build.max_ram_mb", 1024))), 8192))


def build_parallelism() -> int:
    return max(1, min(int(_wagtail_core_value("build_parallelism", get_int("build.parallelism", 1))), 16))


def build_max_wait_minute() -> int:
    return max(1, min(int(_wagtail_core_value("build_wait_minutes", get_int("build.max_wait_minute", 5))), 120))


def build_slot_lease_seconds() -> int:
    return max(60, min(int(_wagtail_core_value("build_slot_lease_seconds", 900)), 86400))


def deploy_timeout_minutes() -> int:
    return max(1, min(int(_wagtail_core_value("deploy_timeout_minutes", get_int("deploy.max_time_minute", 10))), 1440))


def queued_timeout_minutes() -> int:
    return max(1, min(int(_wagtail_core_value("queued_timeout_minutes", deploy_timeout_minutes())), 1440))


def stop_timeout_minutes() -> int:
    return max(1, min(int(_wagtail_core_value("stop_timeout_minutes", 5)), 120))


def unexpected_death_grace_seconds() -> int:
    return max(0, min(int(_wagtail_core_value("unexpected_death_grace_seconds", 15)), 3600))


def monitor_enabled() -> bool:
    return bool(_wagtail_core_value("monitor_enabled", True))


def monitor_interval_seconds() -> int:
    return max(5, min(int(_wagtail_core_value("monitor_interval_seconds", 30)), 3600))


def monitor_batch_size() -> int:
    return max(1, min(int(_wagtail_core_value("monitor_batch_size", 100)), 1000))


def monitor_recovery_enabled() -> bool:
    return bool(_wagtail_core_value("monitor_recovery_enabled", True))


def monitor_max_recovery_attempts() -> int:
    return max(0, min(int(_wagtail_core_value("monitor_max_recovery_attempts", 3)), 10))


def monitor_stale_base_build_minutes() -> int:
    return max(5, min(int(_wagtail_core_value("monitor_stale_base_build_minutes", 30)), 1440))


def monitor_stale_worker_seconds() -> int:
    return max(30, min(int(_wagtail_core_value("monitor_stale_worker_seconds", 90)), 3600))


def monitor_scheduler_lock_seconds() -> int:
    return max(5, min(int(_wagtail_core_value("monitor_scheduler_lock_seconds", 20)), 300))

# ---- Unified Wagtail operator settings -----------------------------------
def base_images_enabled() -> bool:
    return bool(_wagtail_core_value("base_images_enabled", get_bool("base_images.enabled", True)))


def base_images_auto_build() -> bool:
    return bool(_wagtail_core_value("base_images_auto_build", get_bool("base_images.auto_build", True)))


def base_images_auto_register_existing() -> bool:
    return bool(_wagtail_core_value("base_images_auto_register_existing", get_bool("base_images.auto_register_existing", True)))


def base_images_retain_after_deploy() -> bool:
    return bool(_wagtail_core_value("base_images_retain_after_deploy", get_bool("base_images.retain_after_deploy", True)))
