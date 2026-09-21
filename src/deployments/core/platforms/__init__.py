"""
Plugin-based platform detection & inspection system.

Priority (highest wins):
  1. User Config
  2. Auto Detection (from project files)
  3. Platform Defaults
"""

from .registry import PlatformRegistry
from .base.platform import BasePlatform, DetectionResult, ProjectConfig
from .inspector import ProjectInspector

__all__ = [
    "PlatformRegistry",
    "BasePlatform",
    "DetectionResult",
    "ProjectConfig",
    "ProjectInspector",
]
