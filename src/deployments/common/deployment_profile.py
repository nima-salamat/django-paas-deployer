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

    # FastAPI has a dedicated tenant-safe runtime profile. It is kept out of
    # the generic runtime_options escape hatch so operator-only host/runtime
    # controls remain blocked while Uvicorn-specific knobs stay configurable.
    if isinstance(cfg.get("fastapi"), dict):
        from .config import normalize_fastapi_config
        fastapi_warnings: list[str] = []
        runtime["fastapi"] = normalize_fastapi_config(
            cfg.get("fastapi"),
            warnings=fastapi_warnings,
        )
        if fastapi_warnings:
            runtime.setdefault("_config_warnings", []).extend(fastapi_warnings)
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

    # Catalog services are server-owned executable manifests. ``source_kind``
    # is persisted by the revision compiler and is not tenant-controlled.
    # Carry that identity into runtime_options so downstream build/render
    # layers can distinguish a catalog Dockerfile from a generic tenant
    # Dockerfile without trusting an arbitrary tenant flag.
    catalog_managed = str(cfg.get("source_kind") or "").strip().lower() == "catalog"
    if catalog_managed:
        runtime["catalog_managed"] = True

        # A catalog Dockerfile may intentionally own the Docker image
        # ENTRYPOINT (WordPress is one example). The generic renderer entry_point
        # means "replace Dockerfile CMD", so allowing the image-level
        # ENTRYPOINT to leak into this field would cause the renderer to strip
        # the real bootstrap ENTRYPOINT. Existing installations may still have
        # that stale value persisted, so normalize it away when the catalog
        # build context declares an explicit Dockerfile ENTRYPOINT.
        dockerfile = str(cfg.get("dockerfile") or "")
        if re.search(r"^\s*ENTRYPOINT\s+", dockerfile, flags=re.MULTILINE | re.IGNORECASE):
            runtime.pop("entry_point", None)
            runtime.pop("entrypoint", None)
            cfg.pop("entry_point", None)
            cfg.pop("entrypoint", None)

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
