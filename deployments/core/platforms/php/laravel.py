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

        # Permission-critical dirs
        for d in ("storage", "bootstrap/cache"):
            if any(p.startswith(d) for p in file_index) or d in self._dir_hint(file_index):
                result.setdefault("extra", {})
                result["extra"].setdefault("writable_dirs", []).append(d)

        if self._exists("public/index.php", file_index):
            result["static_dir"] = "public"
        return result

    def _dir_hint(self, file_index: dict[str, str]) -> set[str]:
        # reconstruct top-level dirs from file paths
        return {p.split("/")[0] for p in file_index if "/" in p}
