"""
PlatformRegistry – discovers and orders all registered platform plugins.
"""

from __future__ import annotations

from typing import Optional, Type

from .base.platform import BasePlatform, DetectionResult, ProjectConfig
from .inspector import ProjectInspector


class PlatformRegistry:
    """
    Central registry. Plugins register themselves via the decorator
    or by calling register().
    """

    _plugins: list[Type[BasePlatform]] = []

    @classmethod
    def register(cls, plugin: Type[BasePlatform]) -> Type[BasePlatform]:
        if plugin not in cls._plugins:
            cls._plugins.append(plugin)
        return plugin

    @classmethod
    def all_plugins(cls) -> list[Type[BasePlatform]]:
        # Higher priority first
        return sorted(cls._plugins, key=lambda p: -p.priority)

    @classmethod
    def detect(
        cls,
        project_root: str,
        user_config: Optional[dict] = None,
        preferred_platform: Optional[str] = None,
    ) -> tuple[BasePlatform, DetectionResult, ProjectConfig]:
        """
        Full pipeline:
          1. Inspect project
          2. Run every plugin’s detect()
          3. Pick best match (or preferred_platform if forced)
          4. Resolve final config
        """
        inspector = ProjectInspector(project_root).scan()
        file_index = inspector.file_index

        candidates: list[tuple[BasePlatform, DetectionResult]] = []

        for plugin_cls in cls.all_plugins():
            instance = plugin_cls(project_root)
            result = instance.detect(file_index)
            if result is not None:
                candidates.append((instance, result))

        if not candidates:
            # Fallback to a generic platform if one is registered
            for plugin_cls in cls.all_plugins():
                if plugin_cls.name == "generic":
                    instance = plugin_cls(project_root)
                    result = DetectionResult(platform="generic", confidence=0.1)
                    candidates.append((instance, result))
                    break

        if not candidates:
            raise RuntimeError(
                "No platform could be detected and no generic fallback is registered."
            )

        # Prefer explicit user choice
        if preferred_platform:
            for inst, res in candidates:
                if inst.name == preferred_platform or res.framework == preferred_platform:
                    cfg = inst.resolve(file_index, user_config)
                    return inst, res, cfg

        # Highest confidence, then highest plugin priority
        candidates.sort(key=lambda t: (t[1].confidence, t[0].priority), reverse=True)
        best_inst, best_res = candidates[0]
        cfg = best_inst.resolve(file_index, user_config)
        return best_inst, best_res, cfg

    @classmethod
    def list_platforms(cls) -> list[str]:
        return [p.name for p in cls.all_plugins()]
