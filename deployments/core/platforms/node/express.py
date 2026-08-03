"""Express / Fastify backend Node platform."""

from __future__ import annotations

from typing import Any, Optional

from ..base.platform import DetectionResult
from ..registry import PlatformRegistry
from .base_node import NodePlatform


@PlatformRegistry.register
class ExpressPlatform(NodePlatform):
    name = "express"
    priority = 60

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        pkg_paths = self._find("package.json", file_index)
        if not pkg_paths:
            return None
        pkg = self._read_package(file_index, pkg_paths[0])
        fw = pkg.get("framework", "")
        if fw not in ("express", "fastify"):
            return None
        return DetectionResult(
            platform=self.name,
            confidence=0.80,
            framework=fw,
            matched_files=pkg_paths[:2],
            details=pkg,
        )

    def defaults(self) -> dict[str, Any]:
        base = super().defaults()
        base.update(
            {
                "port": 3000,
                "build_command": None,
                "start_command": "node index.js",
            }
        )
        return base

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result = super().inspect(file_index)
        pkg_paths = self._find("package.json", file_index)
        if pkg_paths:
            pkg = self._read_package(file_index, pkg_paths[0])
            main = pkg.get("main") or "index.js"
            result["entrypoint"] = main
            scripts = pkg.get("scripts") or {}
            pm = result.get("package_manager", "npm")
            if scripts.get("start"):
                result["start_command"] = f"{pm} run start"
            else:
                result["start_command"] = f"node {main}"
        return result
