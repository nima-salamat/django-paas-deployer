"""Generic PHP platform."""

from __future__ import annotations

import json
from typing import Any, Optional

from ..base.platform import BasePlatform, DetectionResult
from ..registry import PlatformRegistry


@PlatformRegistry.register
class PHPPlatform(BasePlatform):
    name = "php"
    priority = 40
    marker_files = ["composer.json", "index.php"]

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        has_composer = bool(self._find("composer.json", file_index))
        has_index = bool(self._find("index.php", file_index))
        if not has_composer and not has_index:
            return None
        return DetectionResult(
            platform=self.name,
            confidence=0.55,
            framework="php",
            matched_files=self._find("composer.json", file_index)[:1],
        )

    def defaults(self) -> dict[str, Any]:
        return {
            "port": 80,
            "working_directory": "/var/www/html",
            "install_command": "composer install --no-dev --optimize-autoloader",
            "start_command": "apache2-foreground",
        }

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        composer_paths = self._find("composer.json", file_index)
        if composer_paths:
            try:
                data = json.loads(self._read_text(file_index[composer_paths[0]]))
                require = {**(data.get("require") or {}), **(data.get("require-dev") or {})}
                if "laravel/framework" in require:
                    result["framework"] = "laravel"
                elif "symfony/framework-bundle" in require:
                    result["framework"] = "symfony"
                elif "codeigniter4/framework" in require:
                    result["framework"] = "codeigniter"
                else:
                    result["framework"] = "php"
            except Exception:
                result["framework"] = "php"
        else:
            result["framework"] = "php"

        if self._exists("Dockerfile", file_index):
            result["dockerfile_path"] = "Dockerfile"
        return result
