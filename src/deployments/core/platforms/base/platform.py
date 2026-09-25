"""
BasePlatform – abstract base for every framework plugin.

Hierarchy example:
  BasePlatform
  └── NodePlatform
      ├── ReactPlatform
      ├── NextPlatform
      └── VitePlatform
  └── PythonPlatform
      ├── DjangoPlatform
      ├── FlaskPlatform
      └── FastAPIPlatform
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from .schema import CONFIG_SCHEMA, ConfigOption


@dataclass
class DetectionResult:
    """Result of a platform detection attempt."""

    platform: str
    confidence: float  # 0.0 – 1.0
    framework: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    matched_files: list[str] = field(default_factory=list)


@dataclass
class ProjectConfig:
    """
    Fully resolved configuration after merging:
      Platform Defaults  <  Auto Detection  <  User Config
    """

    platform: str
    framework: Optional[str] = None
    runtime_version: Optional[str] = None
    entrypoint: Optional[str] = None
    build_dir: Optional[str] = None
    install_command: Optional[str] = None
    build_command: Optional[str] = None
    start_command: Optional[str] = None
    port: Optional[int] = None
    working_directory: str = "/app"
    dockerfile_path: Optional[str] = None
    healthcheck: Optional[str] = None
    environment: dict[str, str] = field(default_factory=dict)
    binary: Optional[str] = None
    static_dir: Optional[str] = None
    media_dir: Optional[str] = None
    collectstatic: bool = False
    migrate: bool = False
    seed: bool = False
    output_dir: Optional[str] = None
    publish_dir: Optional[str] = None
    package_manager: Optional[str] = None
    server_type: Optional[str] = None
    celery: bool = False
    celery_beat: bool = False
    # Extra free-form data from detection
    extra: dict[str, Any] = field(default_factory=dict)
    # Provenance – which layer supplied each key
    sources: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in self.__dict__.items()
            if k not in ("sources",) and v is not None
        }


class BasePlatform(ABC):
    """
    Abstract platform plugin.

    Subclasses must implement:
      - name
      - detect()
      - defaults()
      - inspect()
      - validate()
    """

    # Human-readable name, e.g. "django", "nextjs"
    name: str = "base"

    # Higher priority platforms are tried first when confidence is equal
    priority: int = 50

    # Files that strongly indicate this platform (used by inspector)
    marker_files: list[str] = []

    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    @abstractmethod
    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        """
        Return a DetectionResult if this platform matches the project,
        otherwise None.

        file_index maps relative path → absolute path for every interesting
        file discovered by ProjectInspector.
        """
        ...

    # ------------------------------------------------------------------
    # Defaults / Inspection / Validation
    # ------------------------------------------------------------------

    @abstractmethod
    def defaults(self) -> dict[str, Any]:
        """Platform-level default values (lowest priority)."""
        ...

    @abstractmethod
    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        """
        Auto-detect concrete values from the project tree.
        Return a dict of config keys → detected values.
        """
        ...

    def validate(self, config: ProjectConfig) -> list[str]:
        """
        Return a list of human-readable validation errors.
        Empty list = valid.
        """
        errors: list[str] = []
        schema = self.schema()

        for key, option in schema.items():
            value = getattr(config, key, None)
            if option.required and (value is None or value == ""):
                errors.append(f"'{key}' is required for platform '{self.name}'.")
            if value is not None and option.validator:
                ok, msg = option.validator(value)
                if not ok:
                    errors.append(msg or f"Invalid value for '{key}'.")
        return errors

    def schema(self) -> dict[str, ConfigOption]:
        """Override to extend/restrict the global schema."""
        return dict(CONFIG_SCHEMA)

    # ------------------------------------------------------------------
    # Merge engine (Platform Defaults → Auto → User)
    # ------------------------------------------------------------------

    def resolve(
        self,
        file_index: dict[str, str],
        user_config: Optional[dict[str, Any]] = None,
    ) -> ProjectConfig:
        """
        Produce the final ProjectConfig by merging three layers.
        User Config always wins.
        """
        user_config = user_config or {}
        defaults = self.defaults()
        detected = self.inspect(file_index)

        merged: dict[str, Any] = {}
        sources: dict[str, str] = {}

        # 1. Platform defaults
        for k, v in defaults.items():
            if v is not None:
                merged[k] = v
                sources[k] = "platform_default"

        # 2. Auto detection
        for k, v in detected.items():
            if v is not None:
                merged[k] = v
                sources[k] = "auto_detect"

        # 3. User overrides
        for k, v in user_config.items():
            if v is not None:
                merged[k] = v
                sources[k] = "user_config"

        # Build ProjectConfig
        known_fields = set(ProjectConfig.__dataclass_fields__.keys())  # type: ignore
        reserved = {"platform", "framework", "extra", "sources"}
        kwargs = {
            k: v
            for k, v in merged.items()
            if k in known_fields and k not in reserved
        }
        extra: dict[str, Any] = {
            k: v for k, v in merged.items() if k not in known_fields
        }
        # Fold any nested "extra" dict that inspect() may have produced
        nested = merged.get("extra")
        if isinstance(nested, dict):
            extra.update(nested)

        cfg = ProjectConfig(
            platform=self.name,
            framework=merged.get("framework") or self.name,
            extra=extra,
            sources=sources,
            **kwargs,
        )
        return cfg

    # ------------------------------------------------------------------
    # Helpers shared by subclasses
    # ------------------------------------------------------------------

    def _read_text(self, abs_path: str, max_bytes: int = 512_000) -> str:
        try:
            with open(abs_path, "rb") as f:
                raw = f.read(max_bytes)
            return raw.decode("utf-8", errors="ignore")
        except OSError:
            return ""

    def _exists(self, rel: str, file_index: dict[str, str]) -> bool:
        return rel in file_index or any(
            p.endswith("/" + rel) or p == rel for p in file_index
        )

    def _find(self, suffix: str, file_index: dict[str, str]) -> list[str]:
        return [p for p in file_index if p.endswith(suffix) or p == suffix]
