"""React / CRA / Vite-React detection with proper build directory detection."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..base.platform import DetectionResult
from ..registry import PlatformRegistry
from .base_node import NodePlatform


@PlatformRegistry.register
class ReactPlatform(NodePlatform):
    name = "react"
    priority = 70  # higher than plain nodejs

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        pkg_paths = self._find("package.json", file_index)
        if not pkg_paths:
            return None
        pkg = self._read_package(file_index, pkg_paths[0])
        fw = pkg.get("framework", "")
        if fw not in ("react", "cra", "vite-react"):
            return None
        return DetectionResult(
            platform=self.name,
            confidence=0.85,
            framework=fw,
            matched_files=pkg_paths[:2],
            details=pkg,
        )

    def defaults(self) -> dict[str, Any]:
        base = super().defaults()
        base.update(
            {
                "port": 3000,
                "build_dir": "build",  # CRA default
                "build_command": "npm run build",
                "start_command": "npx serve -s build -l 3000",
            }
        )
        return base

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result = super().inspect(file_index)
        pkg_paths = self._find("package.json", file_index)
        if not pkg_paths:
            return result
        pkg = self._read_package(file_index, pkg_paths[0])
        fw = pkg.get("framework", "")

        # Determine build directory and framework type
        if fw in ("vite-react", "vite"):
            # For Vite, try to read vite.config and extract outDir
            vite_out = self._get_vite_out_dir(file_index)
            result["build_dir"] = vite_out or "dist"
            result["framework"] = "vite-react"
        elif fw == "cra":
            result["build_dir"] = "build"
            result["framework"] = "react"
        else:
            # Generic React – check actual build output directory
            # Priority: check for vite.config first, then check dist/build directories
            if self._has_vite_config(file_index):
                vite_out = self._get_vite_out_dir(file_index)
                result["build_dir"] = vite_out or "dist"
                result["framework"] = "vite-react"
            elif "react-scripts" in pkg.get("dependencies", {}) or "react-scripts" in pkg.get("devDependencies", {}):
                result["build_dir"] = "build"
                result["framework"] = "react"
            else:
                # Fallback: check which directory actually exists
                if self._exists("dist", file_index):
                    result["build_dir"] = "dist"
                    result["framework"] = "vite-react"
                elif self._exists("build", file_index):
                    result["build_dir"] = "build"
                    result["framework"] = "react"
                else:
                    result["build_dir"] = "dist"  # Default to dist for Vite

        scripts = pkg.get("scripts") or {}
        pm = result.get("package_manager", "npm")
        
        if scripts.get("build"):
            result["build_command"] = f"{pm} run build"
        
        # Use the detected build_dir in start_command
        build_dir = result.get("build_dir", "build")
        port = result.get("port", 3000)
        if scripts.get("start"):
            # For production we serve the static build
            result["start_command"] = f"npx serve -s {build_dir} -l {port}"
        else:
            result["start_command"] = f"npx serve -s {build_dir} -l {port}"
        
        return result

    def _has_vite_config(self, file_index: dict[str, str]) -> bool:
        """Check if project has vite.config file."""
        return any(
            self._exists(c, file_index)
            for c in ("vite.config.ts", "vite.config.js", "vite.config.mjs")
        )

    def _get_vite_out_dir(self, file_index: dict[str, str]) -> Optional[str]:
        """Extract outDir from vite.config files with improved parsing."""
        for name in ("vite.config.ts", "vite.config.js", "vite.config.mjs"):
            paths = self._find(name, file_index)
            if not paths:
                continue
            text = self._read_text(file_index[paths[0]])
            
            # Try multiple regex patterns for better matching
            patterns = [
                # Pattern 1: outDir: 'dist' or outDir: "dist"
                r"outDir\s*:\s*['\"]([^'\"]+)['\"]",
                # Pattern 2: outDir: path.resolve(__dirname, 'dist')
                r"outDir\s*:\s*path\.resolve\([^,]*,\s*['\"]([^'\"]+)['\"]",
                # Pattern 3: build.outDir
                r"build\s*:\s*\{[^}]*outDir\s*:\s*['\"]([^'\"]+)['\"]",
            ]
            
            for pattern in patterns:
                m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
                if m:
                    return m.group(1).strip()
        
        return None