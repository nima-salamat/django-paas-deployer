"""Laravel platform plugin."""

from __future__ import annotations

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
            if frontend.get("build_command"):
                result["build_command"] = frontend["build_command"]

        return result

    def _detect_frontend(self, file_index: dict[str, str]) -> dict[str, Any]:
        """
        Frontend auto-detection with per-directory marker association.

        Delegates to the shared detection core
        (``deployments.core.project_model``) so the plugin layer, the
        bridge and the Dockerfile renderer all agree on which
        ``package.json`` is the frontend: markers (vite.config.*,
        lockfiles) are associated by shared parent directory and
        candidates are scored, never "first package.json wins".
        """
        from deployments.core.project_model import (
            frontend_candidates,
            select_frontend,
            detect_laravel_roots,
        )

        if not file_index:
            return {}

        names = sorted(file_index.keys())

        def read_file(rel: str):
            abs_path = file_index.get(rel)
            if not abs_path:
                return b""
            try:
                with open(abs_path, "rb") as f:
                    return f.read(512_000)
            except OSError:
                return b""

        laravel_roots = detect_laravel_roots(names, read_file)
        laravel_root = laravel_roots[0] if laravel_roots else ""
        candidates = frontend_candidates(names, read_file, laravel_root)
        best = select_frontend(candidates)
        if best is None:
            return {}

        pm = best["package_manager"]
        return {
            "kind": best["kind"],
            "build_script": best["build_script"],
            "has_package_json": True,
            "package_manager": pm,
            "package_json_path": best["path"],
            "frontend_root": best["root"] or ".",
            "build_command": f"{pm} run {best['build_script']}",
        }

    def _dir_hint(self, file_index: dict[str, str]) -> set[str]:
        return {p.split("/")[0] for p in file_index if "/" in p}
