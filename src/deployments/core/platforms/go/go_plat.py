"""Go platform – prefers cmd/ hierarchy for entrypoint."""

from __future__ import annotations

import os
import re
from typing import Any, Optional

from ..base.platform import BasePlatform, DetectionResult
from ..registry import PlatformRegistry


@PlatformRegistry.register
class GoPlatform(BasePlatform):
    name = "go"
    priority = 70
    marker_files = ["go.mod", "main.go"]

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        if not self._find("go.mod", file_index) and not self._find("main.go", file_index):
            return None
        return DetectionResult(
            platform=self.name,
            confidence=0.90 if self._find("go.mod", file_index) else 0.70,
            framework="go",
            matched_files=self._find("go.mod", file_index)[:1]
            or self._find("main.go", file_index)[:1],
        )

    def defaults(self) -> dict[str, Any]:
        return {
            "port": 8080,
            "working_directory": "/app",
            "build_command": "go build -o main .",
            "start_command": "./main",
            "binary": "main",
            "runtime_version": "1.21",
        }

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        result["runtime_version"] = self._go_version(file_index)

        # Prefer cmd/<name>/main.go
        cmd_mains = [
            p
            for p in file_index
            if p.startswith("cmd/") and p.endswith("/main.go")
        ]
        if cmd_mains:
            # Prefer cmd/api, cmd/server, then alphabetical
            preferred = sorted(
                cmd_mains,
                key=lambda p: (
                    0 if "/api/" in p or p.endswith("cmd/api/main.go") else 1,
                    0 if "/server/" in p else 1,
                    p,
                ),
            )
            chosen = preferred[0]
            # binary name = last directory under cmd/
            parts = chosen.split("/")
            binary = parts[1] if len(parts) >= 3 else "main"
            result["binary"] = binary
            result["entrypoint"] = chosen
            result["build_command"] = f"go build -o {binary} ./{os.path.dirname(chosen)}"
            result["start_command"] = f"./{binary}"
        else:
            # root main.go
            if self._find("main.go", file_index):
                result["entrypoint"] = "main.go"
                result["binary"] = "main"
                result["build_command"] = "go build -o main ."
                result["start_command"] = "./main"

        if self._exists("Dockerfile", file_index):
            result["dockerfile_path"] = "Dockerfile"
        return result

    def _go_version(self, file_index: dict[str, str]) -> Optional[str]:
        for rel in self._find("go.mod", file_index):
            text = self._read_text(file_index[rel])
            m = re.search(r"^go\s+([\d.]+)", text, re.M)
            if m:
                return m.group(1)
        return "1.21"
