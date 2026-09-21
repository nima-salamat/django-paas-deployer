"""Flask platform plugin."""

from __future__ import annotations

import re
from typing import Any, Optional

from ..base.platform import DetectionResult
from ..registry import PlatformRegistry
from .base_python import PythonPlatform


@PlatformRegistry.register
class FlaskPlatform(PythonPlatform):
    name = "flask"
    priority = 70

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        deps = self._collect_deps(file_index)
        if "flask" not in deps:
            # also look for Flask( in source
            found = False
            for rel, abs_p in file_index.items():
                if not rel.endswith(".py"):
                    continue
                if "test" in rel or "migration" in rel:
                    continue
                text = self._read_text(abs_p, max_bytes=80_000)
                if re.search(r"\bFlask\s*\(", text):
                    found = True
                    break
            if not found:
                return None
        return DetectionResult(
            platform=self.name,
            confidence=0.85,
            framework="flask",
        )

    def defaults(self) -> dict[str, Any]:
        base = super().defaults()
        base.update(
            {
                "port": 8000,
                "server_type": "wsgi",
                "start_command": "gunicorn app:app --bind 0.0.0.0:8000 --workers 3",
            }
        )
        return base

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result = super().inspect(file_index)
        result["framework"] = "flask"
        entry = self._find_flask_app(file_index)
        if entry:
            result["entrypoint"] = f"{entry['module']}:{entry['callable']}"
            result["server_type"] = entry.get("type", "wsgi")
            result["start_command"] = self._start_cmd(entry)
        return result

    def _find_flask_app(self, file_index: dict[str, str]) -> Optional[dict]:
        candidates = []
        for rel, abs_p in file_index.items():
            if not rel.endswith(".py") or rel.count("/") > 2:
                continue
            if any(s in rel for s in ("test_", "tests/", "__pycache__", "migrations/")):
                continue
            text = self._read_text(abs_p, max_bytes=100_000)
            module = rel.rsplit(".", 1)[0].replace("/", ".")
            if module.startswith("./"):
                module = module[2:]

            if re.search(r"\bFlask\s*\(", text):
                for name in ("app", "application"):
                    if re.search(rf"\b{name}\s*=\s*Flask\s*\(", text):
                        candidates.append(
                            {"type": "wsgi", "module": module, "callable": name, "prio": 5}
                        )
                        break
                if re.search(r"def\s+create_app\s*\(", text):
                    candidates.append(
                        {
                            "type": "wsgi",
                            "module": module,
                            "callable": "create_app()",
                            "prio": 4,
                        }
                    )
        if not candidates:
            return {"type": "wsgi", "module": "app", "callable": "app"}
        return max(candidates, key=lambda c: c["prio"])

    def _start_cmd(self, entry: dict) -> str:
        target = f"{entry['module']}:{entry['callable'].rstrip('()')}"
        return f"gunicorn {target} --bind 0.0.0.0:8000 --workers 3 --timeout 60"
