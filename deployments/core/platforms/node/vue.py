"""Vue / Nuxt / Vite-Vue platform with improved output detection."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..base.platform import DetectionResult
from ..registry import PlatformRegistry
from .base_node import NodePlatform


@PlatformRegistry.register
class VuePlatform(NodePlatform):
    name = "vuejs"
    priority = 75

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        pkg_paths = self._find("package.json", file_index)
        if not pkg_paths:
            return None
        pkg = self._read_package(file_index, pkg_paths[0])
        fw = pkg.get("framework", "")
        if fw not in ("vue", "nuxt", "vite-vue"):
            return None
        return DetectionResult(
            platform=self.name,
            confidence=0.90 if fw == "nuxt" else 0.85,
            framework=fw,
            matched_files=pkg_paths[:2],
            details=pkg,
        )

    def defaults(self) -> dict[str, Any]:
        base = super().defaults()
        base.update(
            {
                "port": 80,
                "build_dir": "dist",
                "build_command": "npm run build",
                "start_command": "npx serve -s dist -l 80",
            }
        )
        return base

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result = super().inspect(file_index)
        pkg_paths = self._find("package.json", file_index)
        if not pkg_paths:
            return result
        pkg = self._read_package(file_index, pkg_paths[0])
        fw = pkg.get("framework", "vue")
        result["framework"] = fw

        if fw == "nuxt":
            result["build_dir"] = ".output"
            result["port"] = 3000
            result["start_command"] = "node .output/server/index.mjs"
        elif fw == "vite-vue":
            # For Vite-Vue, try to read vite.config
            vite_out = self._get_vite_out_dir(file_index)
            result["build_dir"] = vite_out or "dist"
            port = result.get("port", 80)
            result["start_command"] = f"npx serve -s {result['build_dir']} -l {port}"
        else:
            # Vue CLI or generic Vue
            vue_out = self._get_vue_out_dir(file_index)
            result["build_dir"] = vue_out or "dist"
            port = result.get("port", 80)
            result["start_command"] = f"npx serve -s {result['build_dir']} -l {port}"
        
        return result

    def _get_vue_out_dir(self, file_index: dict[str, str]) -> Optional[str]:
        """Extract output directory from vue.config.js."""
        for name in ("vue.config.js", "vue.config.ts"):
            paths = self._find(name, file_index)
            if not paths:
                continue
            text = self._read_text(file_index[paths[0]])
            
            # Pattern 1: outputDir: 'dist'
            m = re.search(r"outputDir\s*:\s*['\"]([^'\"]+)['\"]", text)
            if m:
                return m.group(1).strip()
            
            # Pattern 2: In module.exports object
            m = re.search(r"outputDir\s*=\s*['\"]([^'\"]+)['\"]", text)
            if m:
                return m.group(1).strip()
        
        return None

    def _get_vite_out_dir(self, file_index: dict[str, str]) -> Optional[str]:
        """Extract outDir from vite.config for Vite-Vue."""
        for name in ("vite.config.ts", "vite.config.js", "vite.config.mjs"):
            paths = self._find(name, file_index)
            if not paths:
                continue
            text = self._read_text(file_index[paths[0]])
            
            # Pattern 1: Direct outDir assignment
            m = re.search(r"outDir\s*:\s*['\"`]([^'\"` ]+)['\"`]", text)
            if m:
                return m.group(1).strip()
            
            # Pattern 2: In build object
            m = re.search(
                r"build\s*:\s*\{[^}]*?outDir\s*:\s*['\"`]([^'\"` ]+)['\"`]",
                text,
                re.DOTALL
            )
            if m:
                return m.group(1).strip()
        
        return None