"""Angular platform plugin with improved build directory detection."""

from __future__ import annotations

import json
from typing import Any, Optional

from ..base.platform import DetectionResult
from ..registry import PlatformRegistry
from .base_node import NodePlatform


@PlatformRegistry.register
class AngularPlatform(NodePlatform):
    name = "angular"
    priority = 75

    def detect(self, file_index: dict[str, str]) -> Optional[DetectionResult]:
        has_angular_json = self._exists("angular.json", file_index)
        pkg_paths = self._find("package.json", file_index)
        if not has_angular_json and not pkg_paths:
            return None
        if pkg_paths:
            pkg = self._read_package(file_index, pkg_paths[0])
            if pkg.get("framework") != "angular" and not has_angular_json:
                return None
        return DetectionResult(
            platform=self.name,
            confidence=0.92,
            framework="angular",
            matched_files=(["angular.json"] if has_angular_json else []) + (pkg_paths[:1] if pkg_paths else []),
        )

    def defaults(self) -> dict[str, Any]:
        base = super().defaults()
        base.update(
            {
                "port": 80,
                "build_dir": "dist",
                "build_command": "npm run build",
                "start_command": "nginx -g daemon off;",
            }
        )
        return base

    def inspect(self, file_index: dict[str, str]) -> dict[str, Any]:
        result = super().inspect(file_index)
        result["framework"] = "angular"
        
        # Try to detect build directory from angular.json
        build_dir = self._angular_out(file_index) or "dist"
        result["build_dir"] = build_dir
        
        # Update start command with detected output directory
        port = result.get("port", 80)
        result["start_command"] = 'nginx -g "daemon off;"'
        
        return result

    def _angular_out(self, file_index: dict[str, str]) -> Optional[str]:
        """
        Extract outputPath from angular.json.
        
        Looks in: projects.{project}.architect.build.options.outputPath
        """
        import json
        
        paths = self._find("angular.json", file_index)
        if not paths:
            return None
        
        try:
            content = self._read_text(file_index[paths[0]])
            data = json.loads(content)
            
            # Navigate to projects and extract outputPath
            projects = data.get("projects") or {}
            
            # Try each project's build configuration
            for proj_name, proj_config in projects.items():
                if not isinstance(proj_config, dict):
                    continue
                
                # Default project or first project with build config
                architect = proj_config.get("architect") or {}
                build_config = architect.get("build") or {}
                options = build_config.get("options") or {}
                output_path = options.get("outputPath")
                
                if output_path:
                    return output_path.strip()
            
            # Fallback: check for defaultProject and use its outputPath
            default_project = data.get("defaultProject")
            if default_project:
                proj = projects.get(default_project, {})
                architect = proj.get("architect", {})
                build_config = architect.get("build", {})
                options = build_config.get("options", {})
                output_path = options.get("outputPath")
                if output_path:
                    return output_path.strip()
        
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        
        return None
