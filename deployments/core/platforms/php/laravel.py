"""Laravel platform plugin."""

from __future__ import annotations

import json
from typing import Any, Optional

from ..base.platform import DetectionResult
from ..registry import PlatformRegistry
from .base_php import PHPPlatform


@PlatformRegistry.register
class LaravelPlatform(PHPPlatform):
    name = "laravel"
    priority = 85

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        has_artisan = self._exists("artisan", file_index)
        composer_paths = self._find("composer.json", file_index)
        is_laravel = False
        if composer_paths:
            text = self._read_text(file_index[composer_paths[0]]).lower()
            if "laravel/framework" in text:
                is_laravel = True
        if not has_artisan and not is_laravel:
            return None
        return DetectionResult(
            platform=self.name,
            confidence=0.95 if has_artisan else 0.85,
            framework="laravel",
            matched_files=(["artisan"] if has_artisan else []) + composer_paths[:1],
        )

    def defaults(self) -> dict[str, Any]:
        base = super().defaults()
        base.update(
            {
                "port": 80,
                "working_directory": "/var/www/html",
                "install_command": "composer install --no-dev --optimize-autoloader",
                "migrate": True,
                "start_command": "apache2-foreground",
            }
        )
        return base

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result = super().inspect(file_index)
        result["framework"] = "laravel"

        for d in ("storage", "bootstrap/cache"):
            if any(p.startswith(d) for p in file_index) or d in self._dir_hint(file_index):
                result.setdefault("extra", {})
                result["extra"].setdefault("writable_dirs", []).append(d)

        if self._exists("public/index.php", file_index):
            result["static_dir"] = "public"
            result["document_root"] = "public"

        # Frontend auto-detection (Deploy.config front_build_platform overrides this)
        frontend = self._detect_frontend(file_index)
        if frontend:
            result.setdefault("extra", {})
            result["extra"]["frontend"] = frontend
            result["front_build_platform"] = frontend.get("kind") or ""
            if frontend.get("build_script"):
                result["build_command"] = f"npm run {frontend['build_script']}"

        return result

    def _detect_frontend(self, file_index: dict[str, str]) -> dict[str, Any]:
        pkg_paths = self._find("package.json", file_index)
        if not pkg_paths:
            return {}

        try:
            pkg = json.loads(self._read_text(file_index[pkg_paths[0]]))
        except Exception:
            return {"kind": "node", "build_script": "build", "has_package_json": True}

        deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
        scripts = pkg.get("scripts") or {}
        if not isinstance(scripts, dict):
            scripts = {}

        build_script = "build"
        for candidate in ("build", "prod", "production", "build:prod", "build:ssr"):
            if candidate in scripts:
                build_script = candidate
                break

        kind = ""
        if (
            self._exists("vite.config.js", file_index)
            or self._exists("vite.config.ts", file_index)
            or self._exists("vite.config.mjs", file_index)
            or "vite" in deps
            or "laravel-vite-plugin" in deps
            or "@vitejs/plugin-react" in deps
            or "@vitejs/plugin-vue" in deps
        ):
            kind = "vite"
        elif "react-scripts" in deps:
            kind = "react"
        elif "laravel-mix" in deps or self._exists("webpack.mix.js", file_index):
            kind = "mix"
        elif "next" in deps:
            kind = "nextjs"
        elif "nuxt" in deps or "nuxt3" in deps:
            kind = "nuxt"
        elif (
            "react" in deps
            or "vue" in deps
            or "@inertiajs/react" in deps
            or "@inertiajs/vue3" in deps
            or "build" in scripts
        ):
            kind = "node"

        if not kind:
            return {}

        return {
            "kind": kind,
            "build_script": build_script,
            "has_package_json": True,
            "package_manager": self._guess_pm(file_index),
        }

    def _guess_pm(self, file_index: dict[str, str]) -> str:
        if self._exists("pnpm-lock.yaml", file_index):
            return "pnpm"
        if self._exists("yarn.lock", file_index):
            return "yarn"
        if self._exists("bun.lockb", file_index):
            return "bun"
        return "npm"

    def _dir_hint(self, file_index: dict[str, str]) -> set[str]:
        return {p.split("/")[0] for p in file_index if "/" in p}
