"""React / CRA / Vite-React detection."""

from __future__ import annotations

from typing import Any, Optional

from ..base.platform import DetectionResult
from ..registry import PlatformRegistry
from .base_node import NodePlatform


@PlatformRegistry.register
class ReactPlatform(NodePlatform):
    name = "react"
    priority = 70  # higher than plain nodejs

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        pkg_paths = self._find("package.json", file_index)
        if not pkg_paths:
            return None
        pkg = self._read_package(file_index, pkg_paths[0])
        fw = pkg.get("framework", "")
        if fw not in ("react", "cra", "vite-react"):
            return None
        return DetectionResult(
            platform=self.name,
            confidence=0.85,
            framework=fw,
            matched_files=pkg_paths[:2],
            details=pkg,
        )

    def defaults(self) -> dict[str, Any]:
        base = super().defaults()
        base.update(
            {
                "port": 3000,
                "build_dir": "build",  # CRA default
                "build_command": "npm run build",
                "start_command": "npx serve -s build -l 3000",
            }
        )
        return base

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result = super().inspect(file_index)
        pkg_paths = self._find("package.json", file_index)
        if not pkg_paths:
            return result
        pkg = self._read_package(file_index, pkg_paths[0])
        fw = pkg.get("framework", "")

        if fw in ("vite-react", "vite"):
            result["build_dir"] = self._vite_out_dir(file_index) or "dist"
            result["framework"] = "vite-react"
        elif fw == "cra":
            result["build_dir"] = "build"
        else:
            # Generic React – prefer build, fall back to dist
            result["build_dir"] = "build" if self._exists("build", file_index) else "dist"

        scripts = pkg.get("scripts") or {}
        pm = result.get("package_manager", "npm")
        if scripts.get("build"):
            result["build_command"] = f"{pm} run build"
        if scripts.get("start"):
            # For production we usually serve the static build
            result["start_command"] = f"npx serve -s {result['build_dir']} -l {result.get('port', 3000)}"
        return result

    def _vite_out_dir(self, file_index: dict[str, str]) -> Optional[str]:
        for name in ("vite.config.ts", "vite.config.js", "vite.config.mjs"):
            paths = self._find(name, file_index)
            if not paths:
                continue
            text = self._read_text(file_index[paths[0]])
            # crude but effective: look for outDir: '...'
            import re
            m = re.search(r"outDir\s*:\s*['\"]([^'\"]+)['\"]", text)
            if m:
                return m.group(1)
        return None
