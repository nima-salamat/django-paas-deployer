"""
Seed SystemSetting rows from the historical hard-coded config.

Imported from CoreConfig.ready() — safe to call multiple times (update_or_create).
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# Snapshot of former core.global_settings.config values + build limits.
DEFAULTS: list[dict] = [
    # ----- mirrors -----
    {
        "key": "mirror.docker",
        "default": "docker.arvancloud.ir",
        "value_type": "string",
        "category": "mirrors",
        "label": "Docker registry mirror",
        "description": "Host used as {MIRROR_DOCKER} in Dockerfile FROM lines.",
    },
    {
        "key": "mirror.python",
        "default": "https://mirror-pypi.runflare.com/simple",
        "value_type": "string",
        "category": "mirrors",
        "label": "PyPI mirror",
        "description": "Index URL used as {MIRROR_PYTHON} for pip install -i.",
    },
    {
        "key": "mirror.npm",
        "default": "https://package-mirror.liara.ir/repository/npm/",
        "value_type": "string",
        "category": "mirrors",
        "label": "npm registry",
        "description": "Optional npm registry mirror for Node builds.",
    },
    {
        "key": "mirror.composer",
        "default": "https://package-mirror.liara.ir/repository/composer/",
        "value_type": "string",
        "category": "mirrors",
        "label": "Composer (PHP) mirror",
        "description": "Optional Composer/packagist mirror used by Laravel/PHP Dockerfiles.",
    },
    {
        "key": "mirror.apt",
        "default": "http://repo.iut.ac.ir/debian/",
        "value_type": "string",
        "category": "mirrors",
        "label": "APT / Debian mirror",
        "description": "Debian package mirror used in Python/Django images.",
    },
    {
        "key": "mirror.go",
        "default": "",
        "value_type": "string",
        "category": "mirrors",
        "label": "Go module proxy",
        "description": "Optional GOPROXY (e.g. https://goproxy.cn,direct).",
    },
    # ----- runtime versions -----
    {
        "key": "runtime.versions",
        "default": {
            "python_version": "3.11",
            "django_python_version": "3.10",
            "node_version": "20",
            "php_version": "8.2",
            "go_version": "1.21",
            "dotnet_version": "6.0",
            "nginx_version": "alpine",
        },
        "value_type": "json",
        "category": "runtime",
        "label": "Default runtime versions",
        "description": "Default language/runtime tags for Dockerfile templates.",
    },
    # ----- ports -----
    {
        "key": "ports.defaults",
        "default": {
            "php": 80,
            "python": None,
            "django": 8000,
            "nextjs": 3000,
            "nodejs": 3000,
            "flask": 5000,
            "docker": None,
            "go": None,
            "statichtmlcss": 80,
            "vuejs": 80,
            "angular": 80,
            "react": 80,
            "dotnet": 5000,
            "mysql": 3306,
            "postgresql": 5432,
            "mariadb": 3306,
            "mongodb": 27017,
            "redis": 6379,
            "oracle": 1521,
        },
        "value_type": "json",
        "category": "ports",
        "label": "Default container ports",
        "description": "Platform → default EXPOSE / publish port.",
    },
    {
        "key": "ports.default_expose",
        "default": 80,
        "value_type": "integer",
        "category": "ports",
        "label": "Fallback EXPOSE port",
        "description": "Used when platform has no default port.",
    },
    # ----- deployment security/resource policy -----
    {
        "key": "deploy.build_pids_limit", "default": 2048, "value_type": "integer",
        "category": "build", "label": "Build PID limit",
        "description": "Operator-only PID cap for untrusted build containers.",
    },
    {
        "key": "deploy.mb_per_worker", "default": 256, "value_type": "integer",
        "category": "runtime", "label": "Memory per worker",
        "description": "Server-side memory budget used to derive process count.",
    },
    {
        "key": "deploy.runtime_worker_cap", "default": 8, "value_type": "integer",
        "category": "runtime", "label": "Runtime worker cap",
        "description": "Hard server-side cap for application worker processes.",
    },
    # ----- build limits (image_manager) -----
    {
        "key": "build.resource_mode",
        "default": "static",
        "value_type": "string",
        "category": "build",
        "label": "Build resource mode",
        "description": "Server-only build budget mode: static or plan. Tenant config cannot change it.",
    },
    {
        "key": "build.max_cpu",
        "default": 1.0,
        "value_type": "float",
        "category": "build",
        "label": "Build max CPU (cores)",
        "description": "NanoCpus limit for docker build containers (DEPLOY_BUILD_MAX_CPU).",
    },
    {
        "key": "build.max_ram_mb",
        "default": 1024,
        "value_type": "integer",
        "category": "build",
        "label": "Build max RAM (MB)",
        "description": "Memory limit for docker build containers (DEPLOY_BUILD_MAX_RAM_MB).",
    },
    {
        "key": "build.parallelism",
        "default": 1,
        "value_type": "integer",
        "category": "build",
        "label": "Build parallelism",
        "description": "Maximum number of Docker builds allowed concurrently across deployment workers.",
    },
    {
        "key": "build.max_wait_minute", "default": 5, "value_type": "integer",
        "category": "build", "label": "Build slot wait timeout (minutes)",
        "description": "Maximum time a deployment waits for a distributed build slot before failing.",
    },
    # ----- deploy behaviour -----
    {
        "key": "deploy.max_time_minute",
        "default": 10,
        "value_type": "integer",
        "category": "deploy",
        "label": "Max deploy time (minutes)",
        "description": "Monitor timeout for stuck deployments (MAX_DEPLOY_TIME_MINUTE).",
    },
    {
        "key": "deploy.worker_count",
        "default": 1,
        "value_type": "integer",
        "category": "deploy",
        "label": "Default worker count",
        "description": "Default gunicorn/celery workers when not set on Deploy.config.",
    },
    {
        "key": "deploy.spa_build_dir",
        "default": "dist",
        "value_type": "string",
        "category": "deploy",
        "label": "Default SPA build dir",
        "description": "Default {build_dir} for Vue/React/Angular nginx stage.",
    },
    {
        "key": "deploy.max_apps",
        "default": 2,
        "value_type": "integer",
        "category": "deploy",
        "label": "Default max apps",
        "description": "Legacy DEFAULT_MAX_APPS (plan overrides preferred).",
    },
    {
        "key": "shell.idle_timeout_minutes",
        "value": "10",
        "category": "shell", "label": "Restricted shell idle timeout (minutes)",
        "description": "Fallback setting for automatically expiring inactive shell sessions.",

        "key": "deploy.pip_timeout",
        "default": 120,
        "value_type": "integer",
        "category": "deploy",
        "label": "pip default timeout (seconds)",
        "description": "PIP_DEFAULT_TIMEOUT injected into Python Dockerfiles.",
    },
    {
        "key": "shell.max_concurrent_sessions_per_service",
        "type": "int",
        "category": "shell",
        "label": "Max concurrent shell sessions per service",
        "description": "How many active restricted shell sessions a single service may have at once (1–20). Configurable in Wagtail/System settings.",
        "default": 1,
        "is_editable": True,
        "is_secret": False,
    },
    {
        "key": "shell.audit_retention_days",
        "type": "int",
        "category": "shell",
        "label": "Shell audit log retention (days)",
        "description": "Audit events older than this many days may be purged by maintenance jobs.",
        "default": 90,
        "is_editable": True,
        "is_secret": False,
    },
    {
        "key": "logging.persistent_enabled",
        "default": True,
        "value_type": "boolean",
        "category": "logging",
        "label": "Persistent runtime logging",
        "description": "When false, runtime logs are not stored.",
        "is_editable": True,
        "is_secret": False,
    },
    {
        "key": "logging.realtime_enabled",
        "default": True,
        "value_type": "boolean",
        "category": "logging",
        "label": "Realtime log streaming",
        "is_editable": True,
        "is_secret": False,
    },
    {
        "key": "logging.default_retention_days",
        "default": 14,
        "value_type": "integer",
        "category": "logging",
        "label": "Default log retention (days)",
        "is_editable": True,
        "is_secret": False,
    },
    {
        "key": "logging.platform_max_retention_days",
        "default": 90,
        "value_type": "integer",
        "category": "logging",
        "label": "Platform max log retention (days)",
        "is_editable": True,
        "is_secret": False,
    },
    {
        "key": "logging.default_storage_mb_per_service",
        "default": 512,
        "value_type": "integer",
        "category": "logging",
        "label": "Default log storage per service (MB)",
        "is_editable": True,
        "is_secret": False,
    },
    {
        "key": "logging.platform_max_storage_mb_per_service",
        "default": 5120,
        "value_type": "integer",
        "category": "logging",
        "label": "Platform max log storage per service (MB)",
        "is_editable": True,
        "is_secret": False,
    },
    {
        "key": "logging.default_ingest_bytes_per_sec",
        "default": 262144,
        "value_type": "integer",
        "category": "logging",
        "label": "Default log ingest rate (bytes/sec)",
        "is_editable": True,
        "is_secret": False,
    },
    {
        "key": "logging.platform_max_ingest_bytes_per_sec",
        "default": 1048576,
        "value_type": "integer",
        "category": "logging",
        "label": "Platform max log ingest rate (bytes/sec)",
        "is_editable": True,
        "is_secret": False,
    },
    {
        "key": "logging.max_entry_size",
        "default": 16384,
        "value_type": "integer",
        "category": "logging",
        "label": "Max log entry size (bytes)",
        "is_editable": True,
        "is_secret": False,
    },
    {
        "key": "logging.default_quota_behavior",
        "default": "fifo_delete",
        "value_type": "string",
        "category": "logging",
        "label": "Default quota behavior",
        "description": "fifo_delete | drop_new | realtime_only",
        "is_editable": True,
        "is_secret": False,
    },


]


def _serialize_default(value, value_type: str) -> str:
    if value_type == "json":
        return json.dumps(value, ensure_ascii=False)
    if value_type == "boolean":
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def seed_system_settings(*, update_existing: bool = False) -> int:
    """
    Ensure every DEFAULTS key exists in DB.

    update_existing=False → only insert missing keys (safe for production).
    update_existing=True  → overwrite values from code defaults (dev reset).
    """
    from core.models import SystemSetting

    created = 0
    for item in DEFAULTS:
        key = item["key"]
        defaults = {
            "value": _serialize_default(item["default"], item["value_type"]),
            "value_type": item["value_type"],
            "category": item["category"],
            "label": item.get("label") or key,
            "description": item.get("description") or "",
            "is_secret": item.get("is_secret", False),
            "is_editable": item.get("is_editable", True),
        }
        obj, was_created = SystemSetting.objects.get_or_create(
            key=key, defaults=defaults
        )
        if was_created:
            created += 1
        elif update_existing:
            for k, v in defaults.items():
                setattr(obj, k, v)
            obj.save()
    if created:
        logger.info("SystemSetting seed: created %s keys", created)
    return created


def seed_dockerfile_templates_from_config() -> int:
    """
    Optionally copy Config.* Dockerfile strings into dockerfile.<platform> keys.
    Only inserts when missing so admin edits are preserved.
    """
    from core.models import SystemSetting

    try:
        from core.global_settings.config import Config
    except Exception:
        return 0

    platforms = [
        "php", "python", "django", "nextjs", "nodejs", "flask", "docker",
        "go", "static", "vue", "angular", "react", "dotnet",
        "vuejs", "statichtmlcss",
    ]
    n = 0
    for name in platforms:
        raw = getattr(Config, name, None)
        if not raw or not isinstance(raw, str):
            continue
        key = f"dockerfile.{name}"
        _, created = SystemSetting.objects.get_or_create(
            key=key,
            defaults={
                "value": raw,
                "value_type": "string",
                "category": "dockerfile",
                "label": f"Dockerfile template: {name}",
                "description": f"Dockerfile template body for platform '{name}'.",
                "is_editable": True,
            },
        )
        if created:
            n += 1
    return n
