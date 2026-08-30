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
]
