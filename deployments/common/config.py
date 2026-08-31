"""
deployments/common/config.py
----------------------------
Single source of truth for parsing ``Deploy.config``.

Previously the codebase had THREE copies of the same JSON-decoding logic
in ``deploy_service.py``, ``tasks.py`` and ``validators.py``.  They
frequently drifted.  This module also adds typed accessors and boolean
coercion so call sites stop hand-rolling ``_as_bool``.
"""

from __future__ import annotations

import json
import re
from typing import Any


def parse_config(raw: Any) -> dict[str, Any]:
    """
    Normalize ``Deploy.config`` to a dict.

    Handles:
      * dict  -> shallow copy
      * JSON-encoded string -> dict
      * double-encoded JSON string (``"\\\"{...}\\\""``) -> dict
      * None / empty / invalid -> empty dict
    """
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str) and parsed.strip():
                parsed2 = json.loads(parsed)
                if isinstance(parsed2, dict):
                    return parsed2
        except (ValueError, TypeError):
            pass
    return {}


# Tenant-controlled config is intentionally narrow. These keys can never
# alter Docker host isolation, resource accounting, or worker orchestration.
TENANT_BLOCKED_KEYS = {
    "resource_limits", "resources", "worker_count", "workers",
    "runtime_options", "extra_host_config", "host_config", "privileged",
    "cap_add", "cap_drop", "security_opt", "devices", "device_requests",
    "pid_mode", "ipc_mode", "uts_mode", "userns_mode", "cgroupns_mode",
    "network_mode", "network", "networks", "volumes", "binds", "labels",
    "cpuset_cpus", "cpu", "memory", "memory_mb", "memory_swap_mb",
    "cpu_shares", "pids_limit", "shm_size", "shm_size_mb",
}

SAFE_BUILD_OPTION_KEYS = {"target", "no_cache", "pull"}


# ---------------------------------------------------------------------------
# Tenant config contract — surface of valid top-level keys
# ---------------------------------------------------------------------------
# Every key listed here is a documented knob a user may set inside
# ``Deploy.config``. Anything NOT in this set is reported back to the user
# as a warning (NOT a hard error — we never want to block a deploy just
# because the user typed an unknown key), so they can fix their config.
# The blocked-keys list above is enforced separately (those keys are
# silently stripped by ``sanitize_tenant_config``).

TENANT_CONFIG_KEYS: dict[str, dict[str, Any]] = {
    "platform": {
        "type": "string",
        "description": "Target platform. Usually auto-detected from the zip "
                       "via /deploy/inspect_zip/. Examples: laravel, php, django, "
                       "flask, python, nodejs, nextjs, react, vuejs, angular, "
                       "go, statichtmlcss, docker.",
    },
    "framework": {
        "type": "string",
        "description": "Framework alias used to refine a Plan.platform. "
                       "Examples: laravel, lumen, symfony, codeigniter, fastapi.",
    },
    "env": {
        "type": "object<string,string>",
        "description": "Environment variables injected at container start. "
                       "Values are stringified before being passed to Docker. "
                       "Do NOT put secrets here for production — use a secrets "
                       "manager instead.",
    },
    "environment": {
        "type": "object<string,string>",
        "description": "Alias for ``env``. ``env`` wins when both are set.",
    },
    "port": {
        "type": "integer",
        "description": "Container EXPOSE / publish port. Falls back to the "
                       "platform default (e.g. 80 for Laravel, 8000 for Django).",
    },
    "entry_point": {
        "type": "string",
        "description": "Replaces the auto-generated CMD in the Dockerfile. "
                       "Validated as a single shell command — no shell "
                       "metacharacters that bypass the validator are allowed.",
    },
    "start_command": {
        "type": "string",
        "description": "Like ``entry_point`` but used as the container start "
                       "command after the image is built.",
    },
    "install_command": {
        "type": "string",
        "description": "Single shell command that installs backend "
                       "dependencies (e.g. ``composer install --no-dev``). "
                       "Validated against the shell-command allow-list.",
    },
    "build_command": {
        "type": "string",
        "description": "Single shell command that builds the project "
                       "(e.g. ``npm run build``). Validated against the "
                       "shell-command allow-list.",
    },
    "package_manager": {
        "type": "string",
        "description": "Package manager used by the build step. "
                       "One of: npm (default), pnpm, yarn, bun.",
    },
    "build_dir": {
        "type": "string",
        "description": "Working directory for the build step, e.g. ``/app`` "
                       "or ``/var/www/html``.",
    },
    "working_directory": {
        "type": "string",
        "description": "Container working directory at runtime. Defaults to "
                       "``/app`` for Python/Node and ``/var/www/html`` for PHP.",
    },
    "static_dir": {
        "type": "string",
        "description": "Path to compiled static assets served by the runtime "
                       "(used by nginx stages for SPAs).",
    },
    "media_dir": {
        "type": "string",
        "description": "Path to user-uploaded media that must persist across "
                       "redeploys (bind-mount target).",
    },
    "server_type": {
        "type": "string",
        "description": "ASGI/WSGI selector for Django (``asgi`` or ``wsgi``). "
                       "Auto-detected when not set.",
    },
    "celery": {
        "type": "boolean",
        "description": "When true, a Celery worker process is added to the "
                       "container via supervisord. Only supported for the "
                       "Python family (django/flask/python).",
    },
    "celery_beat": {
        "type": "boolean",
        "description": "When true (and ``celery`` is true), a Celery beat "
                       "scheduler process is also added.",
    },
    "celery_app": {
        "type": "string",
        "description": "Dotted path to the Celery app module "
                       "(e.g. ``myproj.celery``). Validated against the "
                       "module-name allow-list.",
    },
    "runtime_version": {
        "type": "string",
        "description": "Override the language runtime tag, e.g. ``node20`` "
                       "or ``php8.4``. Parsed by the Dockerfile generator.",
    },
    "node_version":  {"type": "string", "description": "Node.js major version (e.g. ``20``)."},
    "php_version":   {"type": "string", "description": "PHP image tag (e.g. ``8.4``)."},
    "python_version": {"type": "string", "description": "Python image tag (e.g. ``3.11``)."},
    "django_python_version": {"type": "string", "description": "Python tag used by the Django template."},
    "go_version":    {"type": "string", "description": "Go image tag (e.g. ``1.21``)."},
    "dotnet_version":{"type": "string", "description": ".NET SDK tag (e.g. ``6.0``)."},
    "nginx_version": {"type": "string", "description": "Nginx image tag (e.g. ``alpine``)."},
    "front_build_platform": {
        "type": "string",
        "description": "Force the Laravel frontend build kind "
                       "(vite / react / mix / nextjs / nuxt / node). "
                       "Auto-detected from package.json when not set.",
    },
    "frontend": {
        "type": "object",
        "description": "Frontend build options for full-stack PHP/Laravel. "
                       "Accepted keys: ``platform`` / ``kind`` (alias of "
                       "front_build_platform), ``package_manager``, "
                       "``install_command``, ``build_command``, "
                       "``npm_registry`` (override the operator-configured "
                       "``mirror.npm``).",
    },
    "build_options": {
        "type": "object",
        "description": "Safe, allow-listed build metadata. Only ``target``, "
                       "``no_cache`` and ``pull`` are honored; other keys are "
                       "silently dropped.",
    },
    "db_connection": {
        "type": "string",
        "description": "Laravel DB_CONNECTION hint (sqlite / mysql / pgsql / "
                       "sqlsrv). Defaults to sqlite.",
    },
    "database": {
        "type": "string",
        "description": "Alias for ``db_connection``.",
    },
    "laravel": {
        "type": "boolean",
        "description": "Hint that the PHP project is a Laravel app (used "
                       "when the Plan.platform is ``php`` but the zip is "
                       "actually Laravel).",
    },
}


def validate_tenant_config(raw: Any) -> dict[str, Any]:
    """Return a structured report about a tenant-supplied ``Deploy.config``.

    The deploy pipeline never hard-fails on unknown keys — a wrong key is
    usually a typo, not a security threat. Instead we return a dict with:

    * ``warnings``: list of strings the API can surface back to the user.
    * ``blocked_stripped``: list of keys that were silently stripped because
      they are on the operator-only block-list.
    * ``unknown_keys``: list of top-level keys that are not in the contract.
    * ``known_keys``: list of top-level keys that ARE in the contract.

    Callers can attach ``warnings`` to the API response so the user sees a
    clear note like ``"Unknown config key 'enviroment' — did you mean 'env'?"``
    without having their deploy silently succeed with no feedback.
    """
    cfg = parse_config(raw)
    warnings: list[str] = []
    blocked_stripped: list[str] = []
    unknown_keys: list[str] = []
    known_keys: list[str] = []

    for key in cfg.keys():
        skey = str(key)
        if skey in TENANT_BLOCKED_KEYS:
            blocked_stripped.append(skey)
            continue
        if skey in TENANT_CONFIG_KEYS:
            known_keys.append(skey)
        else:
            unknown_keys.append(skey)

    for k in unknown_keys:
        suggestion = _suggest_known_key(k)
        if suggestion:
            warnings.append(
                f"Unknown config key '{k}' — did you mean '{suggestion}'? "
                "It will be ignored by the deployment pipeline."
            )
        else:
            warnings.append(
                f"Unknown config key '{k}'. It will be ignored by the deployment pipeline."
            )

    for k in blocked_stripped:
        warnings.append(
            f"Config key '{k}' is operator-only and was stripped before "
            "persistence. It cannot affect resource limits, workers, "
            "networks, or container privileges."
        )

    return {
        "warnings": warnings,
        "blocked_stripped": blocked_stripped,
        "unknown_keys": unknown_keys,
        "known_keys": known_keys,
        "contract": dict(TENANT_CONFIG_KEYS),
    }


def _suggest_known_key(key: str) -> str | None:
    """Return a close known-key match for a typo (Levenshtein distance <= 2)."""
    s = str(key or "").strip().lower()
    if not s:
        return None
    # Common typos first.
    aliases = {
        "environment": "env",
        "build_cmd": "build_command",
        "install_cmd": "install_command",
        "start_cmd": "start_command",
        "entrypoint": "entry_point",
        "front_build": "front_build_platform",
        "frontend_build": "front_build_platform",
        "frontend_kind": "front_build_platform",
        "db": "database",
        "db_conn": "db_connection",
        "php": "php_version",
        "node": "node_version",
        "python": "python_version",
    }
    if s in aliases:
        return aliases[s]
    best = None
    best_dist = 3
    for known in TENANT_CONFIG_KEYS:
        d = _levenshtein(s, known.lower())
        if d < best_dist:
            best = known
            best_dist = d
    return best if best_dist <= 2 else None


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(
                prev[j] + 1,
                cur[j - 1] + 1,
                prev[j - 1] + (0 if ca == cb else 1),
            ))
        prev = cur
    return prev[-1]


def sanitize_tenant_config(raw: Any) -> dict[str, Any]:
    """Strip tenant escape hatches before config is persisted or executed."""
    cfg = parse_config(raw)
    out = {k: v for k, v in cfg.items() if str(k) not in TENANT_BLOCKED_KEYS}
    build = out.get("build_options") or out.get("build")
    if isinstance(build, dict):
        out["build_options"] = {k: v for k, v in build.items() if k in SAFE_BUILD_OPTION_KEYS}
        out.pop("build", None)
    return out


def as_bool(value: Any) -> bool:
    """Coerce common truthy representations to a real bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def as_int(value: Any, *, default: int, minimum: int | None = None,
           maximum: int | None = None) -> int:
    """Coerce to int with bounds; falls back to ``default`` on error."""
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None:
        result = max(result, minimum)
    if maximum is not None:
        result = min(result, maximum)
    return result


def first_present(*values: Any, skip: tuple = (None, "")) -> Any:
    """Return the first value not in ``skip`` (None / empty string by default)."""
    for v in values:
        if v not in skip:
            return v
    return None


# ---------------------------------------------------------------------------
# Worker count from plan resources
# ---------------------------------------------------------------------------

# Approx RAM (MB) reserved per web worker for Python (Django/Flask/gunicorn).
# Conservative so small plans (256–512 MB) do not OOM under load.
_MB_PER_WEB_WORKER = 256
# Hard cap — even on large plans, unbounded workers hurt more than help.
_MAX_SUGGESTED_WORKERS = 8


def suggest_worker_count(
    max_cpu: Any = None,
    max_ram_mb: Any = None,
    *,
    platform: str | None = None,
    default: int = 1,
    mb_per_worker: int = _MB_PER_WEB_WORKER,
    hard_cap: int = _MAX_SUGGESTED_WORKERS,
) -> int:
    """
    Suggest gunicorn/uvicorn/celery concurrency from plan CPU + RAM.

    Formula
    -------
    * CPU side: roughly one process per allocated CPU core. Fractional CPU
      plans still get one worker, but never scale concurrency above the
      actual CPU budget by default.
    * RAM side: ``max(1, floor(ram_mb / mb_per_worker))``.
    * Result: ``min(cpu_side, ram_side, hard_cap)``, at least ``default``.

    Examples (mb_per_worker=128, hard_cap=8)
    ----------------------------------------
    * 0.5 CPU / 256 MB  → min(1, 2) = 1
    * 1 CPU   / 512 MB  → min(1, 2) = 1
    * 2 CPU   / 1024 MB → min(2, 4) = 2
    * 4 CPU   / 2048 MB → min(4, 8) = 4
    """
    try:
        cpu = float(max_cpu) if max_cpu is not None else 0.0
    except (TypeError, ValueError):
        cpu = 0.0
    try:
        ram = float(max_ram_mb) if max_ram_mb is not None else 0.0
    except (TypeError, ValueError):
        ram = 0.0

    if cpu <= 0 and ram <= 0:
        return max(1, int(default or 1))

    cpu_side = max(1, int(cpu)) if cpu > 0 else hard_cap
    ram_side = (
        max(1, int(ram // max(1, int(mb_per_worker or 128))))
        if ram > 0
        else hard_cap
    )
    suggested = min(cpu_side, ram_side, max(1, int(hard_cap or 8)))
    return max(1, int(default or 1), suggested)


def parse_workers_from_command(cmd: Any) -> int | None:
    """Extract ``--workers N`` / ``-w N`` from a gunicorn/uvicorn command."""
    if not cmd:
        return None
    m = re.search(r"(?:--workers|-w)(?:\s+|=)(\d+)", str(cmd))
    if not m:
        return None
    try:
        n = int(m.group(1))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def apply_workers_to_command(cmd: Any, workers: int) -> str:
    """
    Rewrite ``--workers N`` / ``-w N`` in ``cmd`` to ``workers``.

    If the command has no workers flag, append ``--workers N``.
    Returns the original string unchanged when ``cmd`` is empty.
    """
    text = str(cmd or "").strip()
    if not text:
        return text
    workers = max(1, int(workers or 1))
    if re.search(r"(?:--workers|-w)(?:\s+|=)\d+", text):
        return re.sub(
            r"(?:--workers|-w)(?:\s+|=)\d+",
            f"--workers {workers}",
            text,
            count=1,
        )
    return f"{text} --workers {workers}"


def resolve_resource_limits(raw: Any, *, plan_cpu: Any = None, plan_ram_mb: Any = None) -> dict[str, Any]:
    """Compatibility shim: user resource overrides are intentionally ignored.

    The deployment executor must call deployments.common.resource_policy instead.
    This function remains only so older imports do not break.
    """
    return {}


__all__ = [
    "parse_config",
    "as_bool",
    "as_int",
    "first_present",
    "suggest_worker_count",
    "parse_workers_from_command",
    "apply_workers_to_command",
    "resolve_resource_limits",
    "sanitize_tenant_config",
    "validate_tenant_config",
    "TENANT_CONFIG_KEYS",
    "TENANT_BLOCKED_KEYS",
    "SAFE_BUILD_OPTION_KEYS",
]
