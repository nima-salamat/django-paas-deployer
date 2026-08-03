"""Static HTML/CSS/JS site."""

from __future__ import annotations

from typing import Any, Optional

from ..base.platform import BasePlatform, DetectionResult
from ..registry import PlatformRegistry


@PlatformRegistry.register
class StaticPlatform(BasePlatform):
    name = "statichtmlcss"
    priority = 20  # low – only if nothing else matches

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        has_index = any(
            p.endswith("index.html") or p == "index.html" for p in file_index
        )
        # Avoid claiming if a real framework is present
        if self._find("package.json", file_index) or self._find(
            "requirements.txt", file_index
        ):
            return None
        if not has_index:
            return None
        return DetectionResult(
            platform=self.name,
            confidence=0.40,
            framework="static",
            matched_files=[p for p in file_index if p.endswith("index.html")][:1],
        )

    def defaults(self) -> dict[str, Any]:
        return {
            "port": 80,
            "working_directory": "/usr/share/nginx/html",
            "start_command": 'nginx -g "daemon off;"',
            "build_dir": ".",
        }

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        return {"framework": "static", "build_dir": "."}
