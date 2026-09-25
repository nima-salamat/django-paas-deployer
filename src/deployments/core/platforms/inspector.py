"""
ProjectInspector – Stage 1

Scans a project tree (or a tar/zip extract) for known marker files
and builds a file_index used by all platform plugins.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Marker files the inspector looks for
# ---------------------------------------------------------------------------

KNOWN_MARKERS = frozenset(
    {
        # Node
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lockb",
        "next.config.js",
        "next.config.mjs",
        "next.config.ts",
        "vite.config.js",
        "vite.config.ts",
        "vite.config.mjs",
        "nuxt.config.ts",
        "nuxt.config.js",
        "angular.json",
        "vue.config.js",
        "gatsby-config.js",
        # Python
        "requirements.txt",
        "pyproject.toml",
        "poetry.lock",
        "Pipfile",
        "Pipfile.lock",
        "manage.py",
        "setup.py",
        "setup.cfg",
        # PHP
        "composer.json",
        "composer.lock",
        "artisan",
        # Go
        "go.mod",
        "go.sum",
        "main.go",
        # Rust
        "Cargo.toml",
        "Cargo.lock",
        # Java
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        # Ruby
        "Gemfile",
        "Gemfile.lock",
        # .NET
        "*.csproj",
        "*.fsproj",
        "*.vbproj",
        # Docker / process
        "Dockerfile",
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "Procfile",
        # Generic
        "index.html",
        "index.php",
    }
)

# Directories that strongly hint at a platform
KNOWN_DIRS = frozenset(
    {
        "src",
        "public",
        "dist",
        "build",
        "cmd",
        "app",
        "static",
        "templates",
        "migrations",
        "storage",
        "bootstrap",
        "node_modules",  # presence only, content ignored
    }
)

# Skip these when walking
SKIP_DIRS = frozenset(
    {
        ".git",
        ".svn",
        ".hg",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "vendor",
        "target",
        ".idea",
        ".vscode",
        "coverage",
        ".next",
        ".nuxt",
        "dist",
        "build",
    }
)


class ProjectInspector:
    """
    Walk a project root and produce:
      - file_index  : {relative_path: absolute_path}
      - dir_index   : set of relative directory names
      - markers     : list of found marker file relative paths
    """

    def __init__(self, project_root: str, max_depth: int = 6):
        self.project_root = os.path.abspath(project_root)
        self.max_depth = max_depth
        self.file_index: dict[str, str] = {}
        self.dir_index: set[str] = set()
        self.markers: list[str] = []

    def scan(self) -> "ProjectInspector":
        root = Path(self.project_root)
        if not root.is_dir():
            raise FileNotFoundError(f"Project root does not exist: {self.project_root}")

        for dirpath, dirnames, filenames in os.walk(self.project_root):
            rel_dir = os.path.relpath(dirpath, self.project_root)
            depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
            if depth > self.max_depth:
                dirnames.clear()
                continue

            # Prune skip dirs in-place
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

            if rel_dir != ".":
                self.dir_index.add(rel_dir.replace("\\", "/"))
                top = rel_dir.split(os.sep)[0]
                if top in KNOWN_DIRS:
                    self.dir_index.add(top)

            for name in filenames:
                rel = name if rel_dir == "." else os.path.join(rel_dir, name)
                rel = rel.replace("\\", "/")
                abs_path = os.path.join(dirpath, name)
                self.file_index[rel] = abs_path

                base = os.path.basename(name)
                if base in KNOWN_MARKERS or any(
                    base.endswith(ext) for ext in (".csproj", ".fsproj", ".vbproj")
                ):
                    self.markers.append(rel)

        return self

    def has(self, *names: str) -> bool:
        """True if any of the given relative paths or basenames exist."""
        for n in names:
            if n in self.file_index:
                return True
            if any(p == n or p.endswith("/" + n) for p in self.file_index):
                return True
        return False

    def find(self, suffix: str) -> list[str]:
        return [p for p in self.file_index if p.endswith(suffix) or p == suffix]

    def find_basename(self, basename: str) -> list[str]:
        return [p for p in self.file_index if os.path.basename(p) == basename]
