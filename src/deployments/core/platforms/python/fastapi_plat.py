"""FastAPI / Starlette platform plugin."""

from __future__ import annotations

import re
from typing import Any, Optional

from ..base.platform import DetectionResult
from ..registry import PlatformRegistry
from .base_python import PythonPlatform


@PlatformRegistry.register
class FastAPIPlatform(PythonPlatform):
    name = "fastapi"
    priority = 75

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        deps = self._collect_deps(file_index)
        if "fastapi" in deps or "starlette" in deps:
            return DetectionResult(
                platform=self.name, confidence=0.90, framework="fastapi"
            )
        for rel, abs_p in file_index.items():
            if not rel.endswith(".py"):
                continue
            text = self._read_text(abs_p, max_bytes=80_000)
            if re.search(r"\b(FastAPI|Starlette)\s*\(", text):
                return DetectionResult(
                    platform=self.name, confidence=0.88, framework="fastapi"
                )
        return None

    def defaults(self) -> dict[str, Any]:
        base = super().defaults()
        base.update(
            {
                "port": 8000,
                "server_type": "asgi",
                "start_command": "uvicorn app:app --host 0.0.0.0 --port 8000 --workers 2",
            }
        )
        return base

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result = super().inspect(file_index)
        result["framework"] = "fastapi"
        result["server_type"] = "asgi"
        entry = self._find_app(file_index)
        if entry:
            result["entrypoint"] = f"{entry['module']}:{entry['callable']}"
            result["start_command"] = (
                f"uvicorn {entry['module']}:{entry['callable']} "
                f"--host 0.0.0.0 --port 8000 --workers 2"
            )
        return result

    def _find_app(self, file_index: dict[str, str]) -> Optional[dict]:
        for rel, abs_p in file_index.items():
            if not rel.endswith(".py") or rel.count("/") > 2:
                continue
            text = self._read_text(abs_p, max_bytes=100_000)
            module = rel.rsplit(".", 1)[0].replace("/", ".")
            for name in ("app", "application", "api"):
                if re.search(rf"\b{name}\s*=\s*(FastAPI|Starlette)\s*\(", text):
                    return {"module": module, "callable": name}
        return {"module": "app", "callable": "app"}
