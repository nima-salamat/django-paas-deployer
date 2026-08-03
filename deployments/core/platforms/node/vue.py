"""Vue / Nuxt / Vite-Vue platform."""

from __future__ import annotations

from typing import Any, Optional

from ..base.platform import DetectionResult
from ..registry import PlatformRegistry
from .base_node import NodePlatform


@PlatformRegistry.register
class VuePlatform(NodePlatform):
    name = "vuejs"
    priority = 75

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        pkg_paths = self._find("package.json", file_index)
        if not pkg_paths:
            return None
        pkg = self._read_package(file_index, pkg_paths[0])
        fw = pkg.get("framework", "")
        if fw not in ("vue", "nuxt", "vite-vue"):
            return None
        return DetectionResult(
            platform=self.name,
            confidence=0.90 if fw == "nuxt" else 0.85,
            framework=fw,
            matched_files=pkg_paths[:2],
            details=pkg,
        )

    def defaults(self) -> dict[str, Any]:
        base = super().defaults()
        base.update(
            {
                "port": 80,
                "build_dir": "dist",
                "build_command": "npm run build",
                "start_command": "npx serve -s dist -l 80",
            }
        )
        return base

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result = super().inspect(file_index)
        pkg_paths = self._find("package.json", file_index)
        if not pkg_paths:
            return result
        pkg = self._read_package(file_index, pkg_paths[0])
        fw = pkg.get("framework", "vue")
        result["framework"] = fw

        if fw == "nuxt":
            result["build_dir"] = ".output"
            result["port"] = 3000
            result["start_command"] = "node .output/server/index.mjs"
        else:
            # Vue CLI or Vite-Vue → dist
            result["build_dir"] = "dist"
        return result
