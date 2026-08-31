"""
deployments/core/platform_bridge.py
------------------------------------
Bridge between platforms/ plugins and DeploymentConfig / Orchestrator.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import zipfile
from dataclasses import replace
from typing import Any

from deployments.common.security import (
    is_safe_archive_name,
    is_zip_symlink,
    safe_join,
    validate_final_app_layout,
)
from deployments.common.exceptions import DeploymentSecurityError

from .types import DeploymentConfig

logger = logging.getLogger(__name__)


def _ensure_plugins_loaded() -> None:
    """Side-effect import: registers every platform plugin with the registry."""
    from .platforms import loader  # noqa: F401


# Hard caps matching converter.convert_zip_to_tar.
_MAX_EXTRACT_BYTES = 500 * 1024 * 1024
_MAX_EXTRACT_MEMBERS = 5000


def extract_zip_to_temp(zip_path: str) -> tuple[str, str]:
    """
    Extract deployment ZIP to a temporary directory for filesystem inspection.

    Returns ``(temp_dir, project_root)``.  Caller MUST call
    ``shutil.rmtree(temp_dir)`` when finished.

    Security:
      * Rejects absolute paths, ``../`` traversal, Windows drive prefixes.
      * Rejects symlink + hardlink members (Zip Slip vector).
      * Caps total uncompressed size and member count.
      * Uses ``safe_join`` to assert every member resolves inside ``temp_dir``.
    """
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"ZIP file not found at: {zip_path}")

    temp_dir = tempfile.mkdtemp(prefix="deploy-inspect-")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            total_bytes = 0
            for idx, info in enumerate(zf.infolist()):
                if idx >= _MAX_EXTRACT_MEMBERS:
                    raise ValueError(
                        f"ZIP has too many members (>{_MAX_EXTRACT_MEMBERS})."
                    )
                name = info.filename.replace("\\", "/")
                if not is_safe_archive_name(name):
                    raise DeploymentSecurityError(
                        f"Unsafe path in ZIP: {info.filename}",
                        stage="archive_validation",
                        details={"filename": info.filename},
                    )
                if is_zip_symlink(info):
                    raise DeploymentSecurityError(
                        f"Refusing to extract symlink member '{info.filename}'.",
                        stage="archive_validation",
                        details={"filename": info.filename},
                    )
                # Cap on uncompressed size — guards against zip bombs.
                total_bytes += info.file_size
                if total_bytes > _MAX_EXTRACT_BYTES:
                    raise ValueError(
                        f"ZIP uncompressed size exceeds {_MAX_EXTRACT_BYTES} bytes."
                    )

                # Resolve target and assert it stays inside temp_dir.
                target = safe_join(temp_dir, name)
                if name.endswith("/"):
                    os.makedirs(target, exist_ok=True)
                    continue

                os.makedirs(os.path.dirname(target), exist_ok=True)
                # Force mode 0o644 for files — no executable bits.
                with zf.open(info, "r") as src, open(target, "wb") as dst:
                    import shutil as _shutil
                    _shutil.copyfileobj(src, dst, length=64 * 1024)
                os.chmod(target, 0o644)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    entries = [e for e in os.listdir(temp_dir) if not e.startswith(".")]
    if len(entries) == 1 and os.path.isdir(os.path.join(temp_dir, entries[0])):
        project_root = os.path.join(temp_dir, entries[0])
    else:
        project_root = temp_dir

    # Post-extract gate: refuse any path that escaped the temp root
    # or still contains ".." segments (defense in depth after safe_join).
    try:
        validate_final_app_layout(project_root)
    except DeploymentSecurityError:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return temp_dir, project_root


def enrich_config_from_project(
    config: DeploymentConfig,
    project_root: str,
    *,
    logger_sink=None,
) -> DeploymentConfig:
    """
    Run PlatformRegistry.detect() and fill *empty* fields on DeploymentConfig.

    Priority:
      Values already set on ``config`` (user)  >  Auto-detect  >  Platform defaults
    """
    _ensure_plugins_loaded()
    from .platforms.registry import PlatformRegistry

    user_config: dict[str, Any] = {}
    if config.entry_point:
        user_config["entrypoint"] = config.entry_point
        user_config["start_command"] = config.entry_point
    if config.server_type:
        user_config["server_type"] = config.server_type
    if config.port is not None:
        user_config["port"] = config.port
    if config.environment:
        user_config["environment"] = dict(config.environment)
    if config.celery:
        user_config["celery"] = True
    if config.celery_beat:
        user_config["celery_beat"] = True

    preferred = (config.platform or "").strip().lower() or None
    if preferred in ("", "auto", "detect", "unknown"):
        preferred = None

    try:
        _platform_inst, detection, project_cfg = PlatformRegistry.detect(
            project_root,
            user_config=user_config,
            preferred_platform=preferred,
        )
    except Exception as exc:
        logger.warning(
            "Platform auto-detection failed for %s: %s – continuing with original config.",
            config.name,
            exc,
        )
        if logger_sink:
            try:
                logger_sink.warning(
                    "platform_detection",
                    f"Auto-detection failed: {exc}",
                    progress=11,
                    details={"error": str(exc)},
                )
            except Exception:
                pass
        return config

    if logger_sink:
        try:
            logger_sink.info(
                "platform_detection",
                f"Detected platform='{detection.platform}' "
                f"framework='{detection.framework}' "
                f"confidence={detection.confidence:.2f}",
                progress=12,
                details={
                    "platform": detection.platform,
                    "framework": detection.framework,
                    "confidence": detection.confidence,
                    "matched_files": detection.matched_files,
                    "sources": dict(project_cfg.sources),
                },
            )
        except Exception:
            pass

    updates: dict[str, Any] = {}

    # Only replace platform when caller asked for auto-detect
    if not preferred and project_cfg.platform:
        updates["platform"] = project_cfg.platform

    # Platforms whose detected ``start_command`` must NOT be promoted into
    # ``entry_point`` because the renderer owns CMD/ENTRYPOINT:
    #   * SPA nginx multi-stage images — CMD must stay nginx (no Node).
    #   * PHP family — CMD is ``apache2-foreground`` and the bootstrap
    #     ENTRYPOINT is injected by ``_render_php``.  Promoting the detected
    #     start_command here made ``_render_php`` mistake it for a USER
    #     entry_point override and return early, which silently skipped
    #     composer install AND the Laravel frontend build injection.
    _NO_ENTRYPOINT_PROMOTE = {
        "react", "vue", "vuejs", "angular", "vite", "static", "statichtmlcss",
        "php", "laravel", "lumen", "symfony", "codeigniter",
    }
    _effective_platform = (
        (project_cfg.platform or config.platform or "")
    ).lower()
    if (
        not config.entry_point
        and project_cfg.start_command
        and _effective_platform not in _NO_ENTRYPOINT_PROMOTE
    ):
        updates["entry_point"] = project_cfg.start_command
    else:
        # Still record detected start_command in sources for debugging, but
        # leave entry_point empty so the renderer keeps its own CMD.
        pass

    if not config.server_type and project_cfg.server_type:
        updates["server_type"] = project_cfg.server_type

    # Promote platform detector results into the immutable DeploymentConfig.
    # The old bridge discarded build/install/output settings, which meant a
    # Laravel app could detect React/Vite correctly but the renderer never
    # received the detected commands/directories.
    for source_key, target_key in (
        ("runtime_version", "runtime_version"),
        ("package_manager", "package_manager"),
        ("working_directory", "working_directory"),
        ("build_dir", "build_dir"),
        ("output_dir", "output_dir"),
        ("static_dir", "static_dir"),
        ("start_command", "start_command"),
        ("build_command", "build_command"),
        ("install_command", "install_command"),
    ):
        val = getattr(project_cfg, source_key, None)
        if val not in (None, ""):
            current = getattr(config, target_key, None)
            if current in (None, ""):
                updates[target_key] = val

    if project_cfg.extra:
        # Keep detector-specific capabilities available to renderers.
        updates["runtime_options"] = {
            **(config.runtime_options or {}),
            **dict(project_cfg.extra or {}),
        }

    if config.port is None and project_cfg.port is not None:
        try:
            updates["port"] = int(project_cfg.port)
        except (TypeError, ValueError):
            pass

    if project_cfg.environment:
        merged_env = dict(project_cfg.environment)
        merged_env.update(config.environment or {})
        if merged_env != (config.environment or {}):
            updates["environment"] = merged_env

    # ------------------------------------------------------------------
    # Structured project model — one detection pass whose paths are all
    # relative to the post-flatten build context.  The renderer consumes
    # this instead of re-walking the tar with different wrapper rules.
    # ------------------------------------------------------------------
    try:
        from .project_model import build_project_model_from_tree

        project_model = build_project_model_from_tree(
            _project_file_index(project_root),
            config=config,
            wrapper=_zip_wrapper_name(config.zip_path),
        )
        pm_updates: dict[str, Any] = {"project_model": project_model}
        if project_model.applications:
            app_root = project_model.application_root
            pm_updates["application_root"] = app_root
            # The runtime root is the container path of the application
            # root; for PHP images the app lives at /var/www/html.
            pm_updates["runtime_root"] = (
                "/var/www/html" if app_root == "." else f"/var/www/html/{app_root}"
            )
            if _has_public_index(project_root, app_root):
                pm_updates["document_root"] = (
                    "public" if app_root == "." else f"{app_root}/public"
                )
        if project_model.frontends:
            front = project_model.frontends[0]
            pm_updates["frontend_root"] = front.root or "."
            pm_updates["build_root"] = front.root or "."
            if front.build_output:
                pm_updates["build_output"] = front.build_output
        updates.update(pm_updates)
    except Exception as exc:
        logger.warning(
            "Project model detection failed for %s: %s – renderer will fall back to tar inspection.",
            config.name,
            exc,
        )

    if not updates:
        object.__setattr__(config, "_project_cfg", project_cfg)
        return config

    new_config = replace(config, **updates)
    object.__setattr__(new_config, "_project_cfg", project_cfg)
    return new_config


def _project_file_index(project_root: str) -> "dict[str, str]":
    """Relative posix path → absolute path for the extracted project tree."""
    from .platforms.inspector import ProjectInspector

    return ProjectInspector(project_root).scan().file_index


def _has_public_index(project_root: str, app_root: str) -> bool:
    """True when ``<app_root>/public/index.php`` exists in the tree."""
    import os

    base = project_root if app_root == "." else os.path.join(project_root, app_root)
    return os.path.isfile(os.path.join(base, "public", "index.php"))


def _zip_wrapper_name(zip_path: str) -> "str | None":
    """
    Return the single top-level wrapper directory of the ZIP (the one
    ``flatten_single_toplevel`` will strip), or None.  Best-effort only:
    failures never block the deploy.
    """
    try:
        import os
        import zipfile

        from .project_model import detect_archive_wrapper

        if not zip_path or not os.path.exists(zip_path):
            return None
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = [i.filename for i in zf.infolist()]
        wrapper = detect_archive_wrapper(names)
        return wrapper or None
    except Exception:
        return None


def get_project_model(config: DeploymentConfig):
    """Return the ProjectModel attached by enrich_config_from_project, or None."""
    if config is None:
        return None
    model = getattr(config, "project_model", None)
    if model is not None:
        return model
    return getattr(config, "_project_model", None)


def get_project_cfg(config: DeploymentConfig):
    """Return ProjectConfig attached by enrich_config_from_project, or None."""
    return getattr(config, "_project_cfg", None)

