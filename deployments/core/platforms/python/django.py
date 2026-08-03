"""Django platform – full entrypoint & settings detection."""

from __future__ import annotations

import re
from typing import Any, Optional

from ..base.platform import DetectionResult
from ..registry import PlatformRegistry
from .base_python import PythonPlatform


@PlatformRegistry.register
class DjangoPlatform(PythonPlatform):
    name = "django"
    priority = 90

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        has_manage = bool(self._find("manage.py", file_index))
        deps = self._collect_deps(file_index)
        if not has_manage and "django" not in deps:
            return None
        return DetectionResult(
            platform=self.name,
            confidence=0.95 if has_manage else 0.80,
            framework="django",
            matched_files=self._find("manage.py", file_index)[:1],
        )

    def defaults(self) -> dict[str, Any]:
        base = super().defaults()
        base.update(
            {
                "port": 8000,
                "server_type": None,  # auto
                "collectstatic": True,
                "migrate": True,
                "start_command": None,  # generated
            }
        )
        return base

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result = super().inspect(file_index)
        result["framework"] = "django"

        entry = self._resolve_entrypoint(file_index)
        if entry:
            result["entrypoint"] = entry["module"]
            result["server_type"] = entry["type"]
            result["start_command"] = self._build_start_cmd(entry)

        # settings module
        settings_mod = self._settings_module(file_index)
        if settings_mod:
            result["extra"] = result.get("extra") or {}
            result["django_settings_module"] = settings_mod

        # static / media from settings if possible
        static, media = self._static_media(file_index, settings_mod)
        if static:
            result["static_dir"] = static
        if media:
            result["media_dir"] = media

        return result

    def validate(self, config) -> list[str]:
        errors = super().validate(config)
        if not config.entrypoint and not config.start_command:
            errors.append(
                "Could not detect Django entrypoint. "
                "Ensure manage.py and WSGI_APPLICATION or ASGI_APPLICATION exist, "
                "or supply entrypoint / start_command in user config."
            )
        return errors

    # ------------------------------------------------------------------

    def _settings_module(self, file_index: dict[str, str]) -> Optional[str]:
        for rel in self._find("manage.py", file_index):
            text = self._read_text(file_index[rel])
            text = re.sub(r"#.*", "", text)
            m = re.search(
                r"os\.environ\.setdefault\s*\(\s*['\"]DJANGO_SETTINGS_MODULE['\"]\s*,\s*['\"]([\w.]+)['\"]\s*\)",
                text,
                re.S,
            )
            if m:
                return m.group(1)
            m = re.search(r"DJANGO_SETTINGS_MODULE\s*=\s*['\"]([\w.]+)['\"]", text)
            if m:
                return m.group(1)
        return None

    def _resolve_entrypoint(self, file_index: dict[str, str]) -> Optional[dict]:
        settings_mod = self._settings_module(file_index)
        if not settings_mod:
            return None
        settings_path = settings_mod.replace(".", "/") + ".py"
        candidates = [
            p for p in file_index if p.endswith(settings_path) or p == settings_path
        ]
        if not candidates:
            # try last component only
            leaf = settings_path.split("/")[-1]
            candidates = [p for p in file_index if p.endswith(leaf)]
        if not candidates:
            return None

        text = self._read_text(file_index[candidates[0]])
        for kind, pattern in (
            ("asgi", re.compile(r"(?<!\w)ASGI_APPLICATION\s*=\s*['\"]([\w.]+)['\"]")),
            ("wsgi", re.compile(r"(?<!\w)WSGI_APPLICATION\s*=\s*['\"]([\w.]+)['\"]")),
        ):
            m = pattern.search(text)
            if m:
                module = m.group(1).rsplit(".", 1)[0]
                return {"type": kind, "module": module}
        return None

    def _build_start_cmd(self, entry: dict) -> str:
        module = entry["module"]
        if entry["type"] == "asgi":
            return (
                f"uvicorn {module}:application "
                f"--host 0.0.0.0 --port 8000 --workers 2"
            )
        return (
            f"gunicorn {module}:application "
            f"--bind 0.0.0.0:8000 --workers 3 --timeout 60"
        )

    def _static_media(
        self, file_index: dict[str, str], settings_mod: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        static = media = None
        if not settings_mod:
            return static, media
        settings_path = settings_mod.replace(".", "/") + ".py"
        candidates = [p for p in file_index if p.endswith(settings_path)]
        if not candidates:
            return static, media
        text = self._read_text(file_index[candidates[0]])
        m = re.search(r"STATIC_ROOT\s*=\s*['\"]([^'\"]+)['\"]", text)
        if m:
            static = m.group(1)
        m = re.search(r"MEDIA_ROOT\s*=\s*['\"]([^'\"]+)['\"]", text)
        if m:
            media = m.group(1)
        return static, media
