"""Server-owned resource policy for untrusted deployments.

Users never choose CPU/RAM/PIDs/swap/worker counts.  Runtime resources come
from the selected Service Plan; build resources come only from platform
settings controlled by operators.
"""
from __future__ import annotations

from typing import Any

from django.conf import settings


BUILD_CPU_DEFAULT = 1.0
BUILD_RAM_MB_DEFAULT = 1024
BUILD_PIDS_DEFAULT = 2048
BUILD_SHM_MB_DEFAULT = 64
BUILD_TIMEOUT_MIN_DEFAULT = 15


def _get(name: str, default: Any) -> Any:
    return getattr(settings, name, default)

def _operator(key: str, default: Any) -> Any:
    try:
        from core.settings_service import get_setting
        return get_setting(key, default)
    except Exception:
        return default


def build_limits(plan: Any = None) -> dict[str, int | float]:
    """Return the complete server-owned Docker build resource policy.

    CPU/RAM/PIDs/shared-memory limits are always resolved from operator-owned
    settings. A Service Plan may only participate when the operator selected
    the server-side plan build mode; tenant configuration is never read.
    """
    try:
        from core import settings_service as svc
        mode = svc.build_resource_mode()
        hard_cpu = svc.build_max_cpu()
        hard_ram = svc.build_max_ram_mb()
        pids = svc.build_pids_limit()
        shm = svc.build_shm_mb()
    except Exception:
        mode = str(_operator("build.resource_mode", _get("DEPLOY_BUILD_RESOURCE_MODE", "static"))).strip().lower()
        configured_cpu = _operator("build.max_cpu", _get("DEPLOY_BUILD_MAX_CPU", None))
        configured_ram = _operator("build.max_ram_mb", _get("DEPLOY_BUILD_MAX_RAM_MB", None))
        hard_cpu = max(0.25, min(float(configured_cpu), 8.0)) if configured_cpu not in (None, "") else 8.0
        hard_ram = max(256, min(int(configured_ram), 8192)) if configured_ram not in (None, "") else 8192
        try:
            from core import settings_service as svc
            pids = svc.build_pids_limit()
            shm = svc.build_shm_mb()
        except Exception:
            pids = max(128, min(int(_operator("deploy.build_pids_limit", _get("DEPLOY_BUILD_PIDS_LIMIT", BUILD_PIDS_DEFAULT))), 8192))
            shm = max(16, min(int(_get("DEPLOY_BUILD_SHM_MB", BUILD_SHM_MB_DEFAULT)), 512))

    mode = mode if mode in {"static", "plan"} else "static"
    hard_cpu = max(0.25, min(float(hard_cpu), 8.0))
    hard_ram = max(256, min(int(hard_ram), 8192))
    cpu = min(BUILD_CPU_DEFAULT, hard_cpu)
    ram = min(BUILD_RAM_MB_DEFAULT, hard_ram)
    if mode == "plan" and plan is not None:
        try:
            plan_cpu = float(plan.max_cpu)
            plan_ram = int(float(plan.max_ram))
            if plan_cpu > 0:
                cpu = min(plan_cpu, hard_cpu)
            if plan_ram >= 256:
                ram = min(plan_ram, hard_ram)
        except (TypeError, ValueError):
            pass
    return {"cpu": float(cpu), "memory_mb": int(ram), "pids_limit": int(pids), "shm_size_mb": int(shm), "mode": mode}


_RESOURCE_POLICY_KEYS = frozenset({"cpu", "memory_mb", "pids_limit", "shm_size_mb", "mode"})


def resolve_build_policy(policy: dict[str, Any] | None = None, *, plan: Any = None) -> dict[str, int | float | str]:
    """Resolve a complete policy from the authoritative server-owned policy.

    policy is a server-side snapshot only. Missing fields come from
    build_limits(plan); force_rebuild is a build option, never a resource-policy
    field.
    """
    resolved = dict(build_limits(plan))
    if policy in (None, {}):
        return resolved
    candidate = dict(policy)
    if "force_rebuild" in candidate:
        raise ValueError("force_rebuild is a build option, not part of the resource policy.")
    unknown = set(candidate) - _RESOURCE_POLICY_KEYS
    if unknown:
        raise ValueError("Unsupported build resource policy keys: " + ", ".join(sorted(str(k) for k in unknown)))
    if "mode" in candidate and str(candidate["mode"]).strip().lower() != resolved["mode"]:
        raise ValueError("build resource mode is operator-owned and cannot be overridden.")
    for key in ("cpu", "memory_mb", "pids_limit", "shm_size_mb"):
        if key in candidate:
            resolved[key] = candidate[key]
    try:
        resolved["cpu"] = max(0.25, min(float(resolved["cpu"]), 8.0))
        resolved["memory_mb"] = max(256, min(int(resolved["memory_mb"]), 8192))
        resolved["pids_limit"] = max(128, min(int(resolved["pids_limit"]), 8192))
        resolved["shm_size_mb"] = max(16, min(int(resolved["shm_size_mb"]), 512))
    except (TypeError, ValueError) as exc:
        raise ValueError("Build resource policy contains invalid numeric limits.") from exc
    return resolved

def runtime_limits(plan: Any) -> dict[str, int | float]:
    """Return immutable runtime limits from the Service Plan only."""
    if plan is None:
        raise ValueError("A Service Plan is required to allocate runtime resources.")
    try:
        cpu = float(plan.max_cpu)
        ram = int(float(plan.max_ram))
    except (TypeError, ValueError):
        raise ValueError("Service Plan contains invalid CPU/RAM limits.")
    if cpu <= 0 or ram < 128:
        raise ValueError("Service Plan CPU/RAM limits are invalid.")
    return {"cpu": cpu, "memory_mb": ram}


def worker_count(plan: Any) -> int:
    """Derive process count from the plan; never accept a user override."""
    limits = runtime_limits(plan)
    cpu = limits["cpu"]
    ram = limits["memory_mb"]
    per_worker_mb = max(128, int(_operator("deploy.mb_per_worker", 256)))
    hard_cap = max(1, min(int(_operator("deploy.runtime_worker_cap", 8)), 8))
    cpu_side = max(1, int(float(cpu)))
    ram_side = max(1, int(int(ram) // per_worker_mb))
    return max(1, min(cpu_side, ram_side, hard_cap))
