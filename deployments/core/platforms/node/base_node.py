"""
NodePlatform – shared logic for every Node-based framework.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..base.platform import BasePlatform, DetectionResult
from ..registry import PlatformRegistry


@PlatformRegistry.register
class NodePlatform(BasePlatform):
    name = "nodejs"
    priority = 40
    marker_files = ["package.json"]

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        pkg_paths = self._find("package.json", file_index)
        if not pkg_paths:
            return None
        # Only claim pure Node if no more specific framework matched
        # (more specific plugins have higher priority and run first)
        return DetectionResult(
            platform=self.name,
            confidence=0.55,
            framework="node",
            matched_files=pkg_paths[:3],
            details=self._read_package(file_index, pkg_paths[0]),
        )

    def defaults(self) -> dict[str, Any]:
        return {
            "port": 3000,
            "working_directory": "/app",
            "package_manager": "npm",
            "install_command": "npm ci || npm install",
            "build_command": None,
            "start_command": "npm start",
            "build_dir": None,
        }

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        pkg_paths = self._find("package.json", file_index)
        if not pkg_paths:
            return result

        pkg = self._read_package(file_index, pkg_paths[0])
        result["framework"] = pkg.get("framework", "node")
        result["package_manager"] = self._detect_package_manager(file_index)
        result["install_command"] = self._install_cmd(result["package_manager"])
        result["runtime_version"] = self._node_version(pkg)

        scripts = pkg.get("scripts") or {}
        if scripts.get("build"):
            result["build_command"] = f"{result['package_manager']} run build"
        if scripts.get("start"):
            result["start_command"] = f"{result['package_manager']} run start"
        elif scripts.get("serve"):
            result["start_command"] = f"{result['package_manager']} run serve"
        elif pkg.get("main"):
            result["start_command"] = f"node {pkg['main']}"

        # Dockerfile present?
        for df in ("Dockerfile", "dockerfile"):
            if self._exists(df, file_index):
                result["dockerfile_path"] = df
                break

        return result

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _read_package(self, file_index: dict[str, str], rel: str) -> dict:
        abs_path = file_index.get(rel)
        if not abs_path:
            return {}
        try:
            data = json.loads(self._read_text(abs_path))
        except Exception:
            return {}
        data["framework"] = self._detect_framework(data)
        data["scripts"] = data.get("scripts") or {}
        return data

    def _detect_framework(self, pkg: dict) -> str:
        deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
        if "next" in deps:
            return "nextjs"
        if "nuxt" in deps or "nuxt3" in deps:
            return "nuxt"
        if "gatsby" in deps:
            return "gatsby"
        if "@angular/core" in deps:
            return "angular"
        if "vue" in deps or "@vue/cli-service" in deps:
            return "vue"
        if "react-scripts" in deps:
            return "cra"
        if "vite" in deps and ("react" in deps or "react-dom" in deps):
            return "vite-react"
        if "vite" in deps and "vue" in deps:
            return "vite-vue"
        if "vite" in deps:
            return "vite"
        if "react" in deps or "react-dom" in deps:
            return "react"
        if "express" in deps:
            return "express"
        if "fastify" in deps:
            return "fastify"
        return "node"

    def _detect_package_manager(self, file_index: dict[str, str]) -> str:
        if self._exists("pnpm-lock.yaml", file_index):
            return "pnpm"
        if self._exists("yarn.lock", file_index):
            return "yarn"
        if self._exists("bun.lockb", file_index):
            return "bun"
        if self._exists("package-lock.json", file_index):
            return "npm"
        # packageManager field inside package.json
        pkg_paths = self._find("package.json", file_index)
        if pkg_paths:
            pkg = self._read_package(file_index, pkg_paths[0])
            pm = (pkg.get("packageManager") or "").split("@")[0].lower()
            if pm in ("pnpm", "yarn", "bun", "npm"):
                return pm
        return "npm"

    def _install_cmd(self, pm: str) -> str:
        return {
            "npm": "npm ci || npm install",
            "yarn": "yarn install --frozen-lockfile || yarn install",
            "pnpm": "pnpm install --frozen-lockfile || pnpm install",
            "bun": "bun install",
        }.get(pm, "npm install")

    def _node_version(self, pkg: dict) -> Optional[str]:
        engines = pkg.get("engines") or {}
        node = engines.get("node")
        if node:
            return str(node)
        return None
