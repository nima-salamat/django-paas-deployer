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
    """Return server-owned Docker build limits.

    ``build.resource_mode`` is operator-controlled and defaults to ``static``.
    In ``plan`` mode, the selected Service Plan becomes the *requested* build
    budget, but a separate operator hard ceiling still protects the host.
    A tenant can never select this mode or the resulting numbers.
    """
    mode = str(_operator("build.resource_mode", _get("DEPLOY_BUILD_RESOURCE_MODE", "static"))).strip().lower()
    hard_cpu = max(0.25, min(float(_operator("build.max_cpu", _get("DEPLOY_BUILD_MAX_CPU", BUILD_CPU_DEFAULT))), 8.0))
    hard_ram = max(256, min(int(_operator("build.max_ram_mb", _get("DEPLOY_BUILD_MAX_RAM_MB", BUILD_RAM_MB_DEFAULT))), 8192))

    cpu = hard_cpu
    ram = hard_ram
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

    try:
        from core import settings_service as svc
        pids = svc.build_pids_limit()
        shm = svc.build_shm_mb()
    except Exception:
        pids = max(128, min(int(_operator("deploy.build_pids_limit", _get("DEPLOY_BUILD_PIDS_LIMIT", BUILD_PIDS_DEFAULT))), 8192))
        shm = max(16, min(int(_get("DEPLOY_BUILD_SHM_MB", BUILD_SHM_MB_DEFAULT)), 512))
    return {"cpu": cpu, "memory_mb": ram, "pids_limit": pids, "shm_size_mb": shm, "mode": mode if mode in {"static", "plan"} else "static"}


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
