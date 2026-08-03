"""
PythonPlatform – shared detection for pure Python projects.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from ..base.platform import BasePlatform, DetectionResult
from ..registry import PlatformRegistry


@PlatformRegistry.register
class PythonPlatform(BasePlatform):
    name = "python"
    priority = 35
    marker_files = ["requirements.txt", "pyproject.toml", "Pipfile", "setup.py"]

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        has_req = bool(self._find("requirements.txt", file_index))
        has_pyproject = bool(self._find("pyproject.toml", file_index))
        has_pipfile = bool(self._find("Pipfile", file_index))
        if not (has_req or has_pyproject or has_pipfile):
            return None
        # Let more specific frameworks claim first
        return DetectionResult(
            platform=self.name,
            confidence=0.50,
            framework="python",
            matched_files=self._find("requirements.txt", file_index)[:1],
        )

    def defaults(self) -> dict[str, Any]:
        return {
            "port": 8000,
            "working_directory": "/app",
            "install_command": "pip install --no-cache-dir -r requirements.txt",
            "start_command": "gunicorn app:app --bind 0.0.0.0:8000 --workers 3",
            "runtime_version": "3.11",
            "server_type": "wsgi",
        }

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        result["runtime_version"] = self._python_version(file_index)
        result["install_command"] = self._install_cmd(file_index)

        # Detect popular frameworks from requirements
        deps = self._collect_deps(file_index)
        if "fastapi" in deps:
            result["framework"] = "fastapi"
            result["server_type"] = "asgi"
        elif "flask" in deps:
            result["framework"] = "flask"
            result["server_type"] = "wsgi"
        elif "django" in deps:
            result["framework"] = "django"
        elif "streamlit" in deps:
            result["framework"] = "streamlit"
            result["start_command"] = "streamlit run app.py --server.port 8000 --server.address 0.0.0.0"
        elif "gradio" in deps:
            result["framework"] = "gradio"
        elif "dash" in deps:
            result["framework"] = "dash"

        for df in ("Dockerfile", "dockerfile"):
            if self._exists(df, file_index):
                result["dockerfile_path"] = df
                break
        return result

    def _collect_deps(self, file_index: dict[str, str]) -> set[str]:
        deps: set[str] = set()
        for rel in self._find("requirements.txt", file_index):
            text = self._read_text(file_index[rel])
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                name = re.split(r"[<>=!~\[]", line)[0].strip().lower()
                if name:
                    deps.add(name)
        # pyproject.toml – rough extraction
        for rel in self._find("pyproject.toml", file_index):
            text = self._read_text(file_index[rel]).lower()
            for pkg in ("django", "flask", "fastapi", "streamlit", "gradio", "dash"):
                if pkg in text:
                    deps.add(pkg)
        return deps

    def _python_version(self, file_index: dict[str, str]) -> Optional[str]:
        for rel in self._find("runtime.txt", file_index):
            text = self._read_text(file_index[rel]).strip()
            m = re.search(r"python-?([\d.]+)", text, re.I)
            if m:
                return m.group(1)
        for rel in self._find("pyproject.toml", file_index):
            text = self._read_text(file_index[rel])
            m = re.search(r'python\s*=\s*["\']([^"\']+)["\']', text)
            if m:
                return m.group(1)
        return "3.11"

    def _install_cmd(self, file_index: dict[str, str]) -> str:
        if self._find("poetry.lock", file_index) or (
            self._find("pyproject.toml", file_index)
            and "poetry" in self._read_text(
                file_index[self._find("pyproject.toml", file_index)[0]]
            ).lower()
        ):
            return "poetry install --no-dev --no-interaction"
        if self._find("Pipfile", file_index):
            return "pipenv install --deploy"
        return "pip install --no-cache-dir -r requirements.txt"
