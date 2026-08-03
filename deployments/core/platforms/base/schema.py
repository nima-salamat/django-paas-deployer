"""
Config Schema – every option declares:
  required | optional | auto_detect | default | validator
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ConfigOption:
    name: str
    required: bool = False
    auto_detect: bool = True
    default: Any = None
    description: str = ""
    # validator receives the resolved value and returns (ok: bool, error: str|None)
    validator: Optional[Callable[[Any], tuple[bool, Optional[str]]]] = None


# Canonical schema shared by all platforms. Platforms may extend/override.
CONFIG_SCHEMA: dict[str, ConfigOption] = {
    "runtime_version": ConfigOption(
        name="runtime_version",
        auto_detect=True,
        default=None,
        description="Language / runtime version (e.g. node>=20, python3.11)",
    ),
    "entrypoint": ConfigOption(
        name="entrypoint",
        auto_detect=True,
        default=None,
        description="Application entry module or binary",
    ),
    "build_dir": ConfigOption(
        name="build_dir",
        auto_detect=True,
        default="dist",
        description="Output directory after build",
    ),
    "install_command": ConfigOption(
        name="install_command",
        auto_detect=True,
        default=None,
        description="Dependency install command",
    ),
    "build_command": ConfigOption(
        name="build_command",
        auto_detect=True,
        default=None,
        description="Build / compile command",
    ),
    "start_command": ConfigOption(
        name="start_command",
        auto_detect=True,
        default=None,
        description="Process start command (becomes CMD)",
    ),
    "port": ConfigOption(
        name="port",
        auto_detect=True,
        default=None,
        description="Exposed application port",
    ),
    "working_directory": ConfigOption(
        name="working_directory",
        auto_detect=False,
        default="/app",
        description="WORKDIR inside the container",
    ),
    "dockerfile_path": ConfigOption(
        name="dockerfile_path",
        auto_detect=True,
        default=None,
        description="Path to an existing Dockerfile if present",
    ),
    "healthcheck": ConfigOption(
        name="healthcheck",
        auto_detect=False,
        default=None,
        description="Optional HEALTHCHECK instruction",
    ),
    "environment": ConfigOption(
        name="environment",
        auto_detect=False,
        default={},
        description="Extra runtime environment variables",
    ),
    "binary": ConfigOption(
        name="binary",
        auto_detect=True,
        default=None,
        description="Compiled binary name (Go / Rust / .NET)",
    ),
    "static_dir": ConfigOption(
        name="static_dir",
        auto_detect=True,
        default=None,
        description="Static files directory",
    ),
    "media_dir": ConfigOption(
        name="media_dir",
        auto_detect=True,
        default=None,
        description="Media / uploads directory",
    ),
    "collectstatic": ConfigOption(
        name="collectstatic",
        auto_detect=True,
        default=False,
        description="Whether to run collectstatic (Django)",
    ),
    "migrate": ConfigOption(
        name="migrate",
        auto_detect=True,
        default=False,
        description="Whether to run database migrations",
    ),
    "seed": ConfigOption(
        name="seed",
        auto_detect=False,
        default=False,
        description="Whether to run seeders",
    ),
    "output_dir": ConfigOption(
        name="output_dir",
        auto_detect=True,
        default=None,
        description="Alias for build_dir (frontend)",
    ),
    "publish_dir": ConfigOption(
        name="publish_dir",
        auto_detect=True,
        default=None,
        description="Publish directory (.NET)",
    ),
    "package_manager": ConfigOption(
        name="package_manager",
        auto_detect=True,
        default="npm",
        description="Detected package manager (npm/yarn/pnpm/bun)",
    ),
    "server_type": ConfigOption(
        name="server_type",
        auto_detect=True,
        default=None,
        description="asgi | wsgi (Python)",
    ),
    "celery": ConfigOption(
        name="celery",
        auto_detect=False,
        default=False,
        description="Enable Celery worker",
    ),
    "celery_beat": ConfigOption(
        name="celery_beat",
        auto_detect=False,
        default=False,
        description="Enable Celery beat",
    ),
}
