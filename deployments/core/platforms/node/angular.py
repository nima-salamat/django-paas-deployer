"""Angular platform plugin."""

from __future__ import annotations

from typing import Any, Optional

from ..base.platform import DetectionResult
from ..registry import PlatformRegistry
from .base_node import NodePlatform


@PlatformRegistry.register
class AngularPlatform(NodePlatform):
    name = "angular"
    priority = 75

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        has_angular_json = self._exists("angular.json", file_index)
        pkg_paths = self._find("package.json", file_index)
        if not has_angular_json and not pkg_paths:
            return None
        if pkg_paths:
            pkg = self._read_package(file_index, pkg_paths[0])
            if pkg.get("framework") != "angular" and not has_angular_json:
                return None
        return DetectionResult(
            platform=self.name,
            confidence=0.92,
            framework="angular",
            matched_files=(["angular.json"] if has_angular_json else []) + (pkg_paths[:1] if pkg_paths else []),
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
        result["framework"] = "angular"
        # angular.json can define outputPath
        result["build_dir"] = self._angular_out(file_index) or "dist"
        return result

    def _angular_out(self, file_index: dict[str, str]) -> Optional[str]:
        import json, re
        paths = self._find("angular.json", file_index)
        if not paths:
            return None
        try:
            data = json.loads(self._read_text(file_index[paths[0]]))
            # walk projects.*.architect.build.options.outputPath
            for proj in (data.get("projects") or {}).values():
                opts = (
                    (proj.get("architect") or {})
                    .get("build", {})
                    .get("options", {})
                )
                if opts.get("outputPath"):
                    return opts["outputPath"]
        except Exception:
            pass
        return None
