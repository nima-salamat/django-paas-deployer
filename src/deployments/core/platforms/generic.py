"""Generic fallback platform – always available."""

from __future__ import annotations

from typing import Any, Optional

from .base.platform import BasePlatform, DetectionResult
from .registry import PlatformRegistry


@PlatformRegistry.register
class GenericPlatform(BasePlatform):
    name = "generic"
    priority = 1

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        return DetectionResult(
            platform=self.name,
            confidence=0.05,
            framework="generic",
        )

    def defaults(self) -> dict[str, Any]:
        return {
            "port": 8080,
            "working_directory": "/app",
            "start_command": None,
        }

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self._exists("Dockerfile", file_index):
            result["dockerfile_path"] = "Dockerfile"
        if self._exists("Procfile", file_index):
            text = self._read_text(file_index["Procfile"])
            for line in text.splitlines():
                if line.startswith("web:"):
                    result["start_command"] = line[4:].strip()
                    break
        return result
