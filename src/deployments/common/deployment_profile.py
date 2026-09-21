"""Deployment profile normalization for the public Deploy.config contract."""
from __future__ import annotations
from typing import Any

from .config import as_bool, as_int, sanitize_tenant_config


def normalize_profile(raw: Any, *, plan_cpu=None, plan_ram_mb=None) -> dict[str, Any]:
    cfg = sanitize_tenant_config(raw)
    # Resource limits are deliberately NOT part of the public user config.
    # The execution layer derives runtime limits from the Service Plan and
    # build limits from operator-owned server policy.
    resources = {}
    build = dict(cfg.get("build_options") or cfg.get("build") or {})
    runtime = dict(cfg.get("runtime_options") or cfg.get("runtime") or {})
    frontend = cfg.get("frontend")
    if isinstance(frontend, dict):
        frontend = dict(frontend)
        for key, value in frontend.items():
            build.setdefault(key, value)
    else:
        frontend = {}

    # Backward-compatible aliases.
    aliases = {
        "build_target": "target",
        "build_network": "network",
        "buildargs": "build_args",
        "nocache": "no_cache",
    }
    for src, dst in aliases.items():
        if src in cfg and dst not in build:
            build[dst] = cfg[src]

    for key in ("build_command", "install_command", "package_manager", "build_dir", "runtime_version", "output_dir", "build_target", "build_args", "build_network", "no_cache", "pull"):
        if key in cfg and key not in build:
            build[key] = cfg[key]

    for key in ("start_command", "working_directory", "healthcheck", "restart_policy", "ports", "read_only", "user", "command", "entrypoint"):
        if key in cfg and key not in runtime:
            runtime[key] = cfg[key]

    out = dict(cfg)
    out.pop("resource_limits", None)
    out.pop("resources", None)
    out["resource_limits"] = resources
    out["build_options"] = build
    out["runtime_options"] = runtime
    out["frontend"] = frontend
    # Ignore user-supplied worker_count; the worker count is derived from the plan.
    out.pop("worker_count", None)
    if "celery" in out:
        out["celery"] = as_bool(out["celery"])
    if "celery_beat" in out:
        out["celery_beat"] = as_bool(out["celery_beat"]) and out.get("celery", False)
    return out
