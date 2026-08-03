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

from .types import DeploymentConfig

logger = logging.getLogger(__name__)


def _ensure_plugins_loaded() -> None:
    """Side-effect import: registers every platform plugin with the registry."""
    from .platforms import loader  # noqa: F401


def extract_zip_to_temp(zip_path: str) -> tuple[str, str]:
    """
    Extract deployment ZIP to a temporary directory for filesystem inspection.

    Returns (temp_dir, project_root).
    Caller MUST call shutil.rmtree(temp_dir) when finished.
    """
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"ZIP file not found at: {zip_path}")

    temp_dir = tempfile.mkdtemp(prefix="deploy-inspect-")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or name.startswith("../") or "/../" in name:
                    raise ValueError(f"Unsafe path in ZIP: {info.filename}")
            zf.extractall(temp_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    entries = [e for e in os.listdir(temp_dir) if not e.startswith(".")]
    if len(entries) == 1 and os.path.isdir(os.path.join(temp_dir, entries[0])):
        project_root = os.path.join(temp_dir, entries[0])
    else:
        project_root = temp_dir

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

    if not config.entry_point and project_cfg.start_command:
        updates["entry_point"] = project_cfg.start_command

    if not config.server_type and project_cfg.server_type:
        updates["server_type"] = project_cfg.server_type

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

    if not updates:
        object.__setattr__(config, "_project_cfg", project_cfg)
        return config

    new_config = replace(config, **updates)
    object.__setattr__(new_config, "_project_cfg", project_cfg)
    return new_config


def get_project_cfg(config: DeploymentConfig):
    """Return ProjectConfig attached by enrich_config_from_project, or None."""
    return getattr(config, "_project_cfg", None)
