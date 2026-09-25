"""Next.js platform plugin."""

from __future__ import annotations

from typing import Any, Optional

from ..base.platform import DetectionResult
from ..registry import PlatformRegistry
from .base_node import NodePlatform


@PlatformRegistry.register
class NextPlatform(NodePlatform):
    name = "nextjs"
    priority = 80

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        pkg_paths = self._find("package.json", file_index)
        if not pkg_paths:
            return None
        pkg = self._read_package(file_index, pkg_paths[0])
        if pkg.get("framework") != "nextjs":
            # also accept next.config.* without next in package.json (rare)
            if not any(
                self._exists(c, file_index)
                for c in ("next.config.js", "next.config.mjs", "next.config.ts")
            ):
                return None
        return DetectionResult(
            platform=self.name,
            confidence=0.95,
            framework="nextjs",
            matched_files=pkg_paths[:2],
            details=pkg,
        )

    def defaults(self) -> dict[str, Any]:
        base = super().defaults()
        base.update(
            {
                "port": 3000,
                "build_dir": ".next",
                "build_command": "npm run build",
                "start_command": "npm start",
            }
        )
        return base

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result = super().inspect(file_index)
        result["framework"] = "nextjs"
        result["build_dir"] = ".next"

        # Detect output mode from next.config
        output_mode = self._next_output_mode(file_index)
        if output_mode == "export":
            result["build_dir"] = "out"
            result["start_command"] = "npx serve -s out -l 3000"
            result["extra"] = result.get("extra") or {}
            result["output_mode"] = "export"
        elif output_mode == "standalone":
            result["output_mode"] = "standalone"
            result["start_command"] = "node .next/standalone/server.js"

        return result

    def _next_output_mode(self, file_index: dict[str, str]) -> Optional[str]:
        import re
        for name in ("next.config.js", "next.config.mjs", "next.config.ts"):
            paths = self._find(name, file_index)
            if not paths:
                continue
            text = self._read_text(file_index[paths[0]])
            if re.search(r"output\s*:\s*['\"]export['\"]", text):
                return "export"
            if re.search(r"output\s*:\s*['\"]standalone['\"]", text):
                return "standalone"
        return None
