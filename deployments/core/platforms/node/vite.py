"""Pure Vite (non-React/Vue) platform."""

from __future__ import annotations

from typing import Any, Optional

from ..base.platform import DetectionResult
from ..registry import PlatformRegistry
from .base_node import NodePlatform


@PlatformRegistry.register
class VitePlatform(NodePlatform):
    name = "vite"
    priority = 65

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        has_vite_config = any(
            self._exists(c, file_index)
            for c in ("vite.config.ts", "vite.config.js", "vite.config.mjs")
        )
        pkg_paths = self._find("package.json", file_index)
        if not pkg_paths and not has_vite_config:
            return None
        if pkg_paths:
            pkg = self._read_package(file_index, pkg_paths[0])
            fw = pkg.get("framework", "")
            # Let ReactPlatform / VuePlatform claim vite-react / vite-vue
            if fw in ("vite-react", "vite-vue", "nextjs", "nuxt", "angular", "cra"):
                return None
            if "vite" not in fw and not has_vite_config:
                return None
        return DetectionResult(
            platform=self.name,
            confidence=0.80,
            framework="vite",
            matched_files=pkg_paths[:2] if pkg_paths else [],
        )

    def defaults(self) -> dict[str, Any]:
        base = super().defaults()
        base.update(
            {
                "port": 4173,
                "build_dir": "dist",
                "build_command": "npm run build",
                "start_command": "npx serve -s dist -l 4173",
            }
        )
        return base

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result = super().inspect(file_index)
        result["framework"] = "vite"
        result["build_dir"] = self._out_dir(file_index) or "dist"
        return result

    def _out_dir(self, file_index: dict[str, str]) -> Optional[str]:
        import re
        for name in ("vite.config.ts", "vite.config.js", "vite.config.mjs"):
            paths = self._find(name, file_index)
            if not paths:
                continue
            text = self._read_text(file_index[paths[0]])
            m = re.search(r"outDir\s*:\s*['\"]([^'\"]+)['\"]", text)
            if m:
                return m.group(1)
        return None
