"""FastAPI platform plugin.

FastAPI is treated as a first-class ASGI platform rather than a Flask/Python
fallback. Detection is based on FastAPI dependency/import evidence and the
actual ASGI application object in the uploaded project.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from ..base.platform import DetectionResult
from ..registry import PlatformRegistry
from .base_python import PythonPlatform
from ...entrypoints import resolve_python_runtime_context


_APP_ASSIGNMENT_RE = re.compile(
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<factory>(?:fastapi\.)?FastAPI)\s*\(",
    re.MULTILINE,
)


@PlatformRegistry.register
class FastAPIPlatform(PythonPlatform):
    name = "fastapi"
    priority = 82

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        deps = self._collect_deps(file_index)

        if "fastapi" in deps:
            return DetectionResult(
                platform=self.name,
                confidence=0.96,
                framework="fastapi",
                matched_files=self._find_dependency_manifests(file_index),
            )

        for rel, abs_p in file_index.items():
            if not rel.endswith(".py"):
                continue
            if _SKIP_SOURCE_RE.search(rel):
                continue
            text = self._read_text(abs_p, max_bytes=100_000)
            if _is_fastapi_source(text):
                return DetectionResult(
                    platform=self.name,
                    confidence=0.93,
                    framework="fastapi",
                    matched_files=[rel],
                )
        return None

    def defaults(self) -> dict[str, Any]:
        base = super().defaults()
        base.update(
            {
                "port": 8000,
                "working_directory": "/app",
                "server_type": "asgi",
                # Do not invent app:app. A real entrypoint is required unless
                # the tenant explicitly supplies a start/entry command.
                "start_command": None,
            }
        )
        return base

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result = super().inspect(file_index)
        result["framework"] = "fastapi"
        result["server_type"] = "asgi"

        entry = self._find_app(file_index)
        if entry:
            context = resolve_python_runtime_context(file_index.keys(), entry["module"])
            target = f"{context['module']}:{entry['callable']}"
            result["entrypoint"] = target
            result["working_directory"] = context["working_directory"]
            app_dir_arg = (
                f" --app-dir {context['working_directory']}"
                if context["source_root"]
                else ""
            )
            result["start_command"] = (
                f"uvicorn {target} --host 0.0.0.0 --port 8000{app_dir_arg}"
            )
            result["fastapi_entrypoint_detected"] = True
            result["fastapi_entrypoint_source"] = entry["source"]
            result["extra"] = {
                **(result.get("extra") or {}),
                "source_root": context["source_root"],
                "runtime_module": context["module"],
                "runtime_working_directory": context["working_directory"],
            }
        else:
            result["fastapi_entrypoint_detected"] = False
            result["fastapi_entrypoint_source"] = None
        return result

    def validate(self, config: Any) -> list[str]:
        errors = list(super().validate(config) or [])
        has_target = bool(
            str(getattr(config, "entrypoint", "") or "").strip()
            or str(getattr(config, "start_command", "") or "").strip()
        )
        if not has_target:
            errors.append(
                "FastAPI entrypoint could not be detected. "
                "Add a FastAPI app such as 'app = FastAPI()' or set entry_point/start_command explicitly."
            )
        return errors

    def _find_app(self, file_index: dict[str, str]) -> Optional[dict[str, str]]:
        candidates: list[dict[str, str | int]] = []

        ordered = sorted(
            file_index.items(),
            key=lambda item: (
                _preferred_module_rank(item[0]),
                item[0].count("/"),
                item[0],
            ),
        )

        for rel, abs_p in ordered:
            if not rel.endswith(".py") or _SKIP_SOURCE_RE.search(rel):
                continue
            text = self._read_text(abs_p, max_bytes=120_000)
            if not _is_fastapi_source(text):
                continue

            module = rel.rsplit(".", 1)[0].replace("/", ".").lstrip(".")
            for match in _APP_ASSIGNMENT_RE.finditer(text):
                name = match.group("name")
                priority = 100 if name == "app" else 90 if name == "application" else 80 if name == "api" else 70
                priority += _preferred_module_rank(rel)
                candidates.append(
                    {
                        "module": module,
                        "callable": name,
                        "source": rel,
                        "_priority": priority,
                    }
                )

        if not candidates:
            return None

        best = max(candidates, key=lambda item: int(item["_priority"]))
        return {
            "module": str(best["module"]),
            "callable": str(best["callable"]),
            "source": str(best["source"]),
        }

    def _find_dependency_manifests(self, file_index: dict[str, str]) -> list[str]:
        out: list[str] = []
        for name in ("requirements.txt", "pyproject.toml", "Pipfile"):
            out.extend(self._find(name, file_index)[:1])
        return out


_SKIP_SOURCE_RE = re.compile(
    r"(?:^|/)(?:tests?|test_|__pycache__|migrations?)(?:/|$)|"
    r"(?:^|/)test_[^/]+\.py$",
    re.IGNORECASE,
)


def _preferred_module_rank(path: str) -> int:
    basename = path.rsplit("/", 1)[-1].lower()
    return {
        "main.py": 30,
        "app.py": 25,
        "server.py": 20,
        "api.py": 18,
    }.get(basename, 0)


def _is_fastapi_source(text: str) -> bool:
    # The constructor is the strongest source-level signal and also handles
    # multiline imports / aliased imports that a single-line import regex misses.
    return bool(
        _APP_ASSIGNMENT_RE.search(text)
        and (
            re.search(r"\bFastAPI\s*\(", text)
            or re.search(r"\bfastapi\.FastAPI\s*\(", text)
        )
    )
