"""Strong contract tests for the structured deployment project model."""

from __future__ import annotations

import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from deployments.core.project_model import (
    ProjectRoot,
    TarFileView,
    build_project_model_from_tar,
    build_project_model_from_tree,
    detect_archive_wrapper,
    detect_build_output,
    package_manager_for,
    select_frontend,
)


def make_tar(files: dict[str, str]) -> io.BytesIO:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        for name, value in files.items():
            data = value.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    stream.seek(0)
    return stream


class ArchiveStructureContracts(unittest.TestCase):
    def test_archive_wrapper_is_detected_only_for_real_single_wrappers(self):
        self.assertEqual(
            detect_archive_wrapper({"release/src/main.py", "release/requirements.txt"}),
            "release",
        )
        self.assertEqual(
            detect_archive_wrapper({"main.py", "release/main.py"}),
            "",
        )
        self.assertEqual(
            detect_archive_wrapper({"release/"}),
            "",
        )

    def test_archive_wrapper_ignores_generated_dockerfile_entries(self):
        self.assertEqual(
            detect_archive_wrapper({"release/main.py", "Dockerfile", ".dockerignore"}),
            "release",
        )

    def test_archive_wrapper_rejects_refused_system_directories(self):
        for name in ("etc", "usr", "var", "tmp", "proc"):
            with self.subTest(name=name):
                self.assertEqual(
                    detect_archive_wrapper({f"{name}/main.py"}),
                    "",
                )

    def test_archive_wrapper_rejects_flatten_collisions(self):
        self.assertEqual(
            detect_archive_wrapper({"release/app/main.py", "app/other.py"}),
            "",
        )

    def test_tar_file_view_indexes_original_and_post_flatten_names(self):
        view = TarFileView(make_tar({
            "release/package.json": '{"name":"demo"}',
            "release/src/main.py": "x = 1\n",
        }))
        self.assertIn("release/package.json", view.names())
        self.assertEqual(view.read("package.json"), b'{"name":"demo"}')
        self.assertEqual(view.read("src/main.py"), b"x = 1\n")
        self.assertIsNone(view.read("missing.txt"))

    def test_tar_file_view_rejects_parent_traversal_entries(self):
        view = TarFileView(make_tar({
            "../escape.txt": "bad",
            "safe.txt": "good",
        }))
        self.assertEqual(view.read("safe.txt"), b"good")
        self.assertIsNone(view.read("../escape.txt"))

    def test_package_manager_selection_is_deterministic(self):
        self.assertEqual(package_manager_for({"packageManager": "pnpm@10"}, {"package-lock.json"}), "pnpm")
        self.assertEqual(package_manager_for({}, {"pnpm-lock.yaml"}), "pnpm")
        self.assertEqual(package_manager_for({}, {"yarn.lock"}), "yarn")
        self.assertEqual(package_manager_for({}, {"bun.lock"}), "bun")
        self.assertEqual(package_manager_for({}, {"package-lock.json", "pnpm-lock.yaml"}), "npm")
        self.assertEqual(package_manager_for({}, set()), "npm")

    def test_frontend_selection_excludes_unrecognized_candidates(self):
        result = select_frontend([
            {"kind": None, "score": 999, "root": "", "path": "bad/package.json"},
            {"kind": "vite", "score": 90, "root": "frontend", "path": "frontend/package.json"},
        ])
        self.assertIsNotNone(result)
        self.assertEqual(result["kind"], "vite")

    def test_frontend_selection_tiebreaks_by_shallow_root_then_path(self):
        result = select_frontend([
            {"kind": "vite", "score": 100, "root": "frontend/nested", "path": "frontend/nested/package.json"},
            {"kind": "vite", "score": 100, "root": "frontend", "path": "frontend/package.json"},
            {"kind": "vite", "score": 100, "root": "web", "path": "web/package.json"},
        ])
        self.assertEqual(result["root"], "frontend")

    def test_build_output_mapping_matches_framework_semantics(self):
        self.assertEqual(
            detect_build_output("vite", {"laravel-vite-plugin": "1"}, "frontend", "backend"),
            "backend/public/build",
        )
        self.assertEqual(
            detect_build_output("mix", {}, "frontend", "backend"),
            "backend/public",
        )
        self.assertEqual(
            detect_build_output("react", {}, "frontend", ""),
            "frontend/build",
        )
        self.assertEqual(
            detect_build_output("vite", {}, "frontend", ""),
            "frontend/dist",
        )

    def test_build_project_model_from_wrapped_tar_preserves_post_flatten_paths(self):
        model = build_project_model_from_tar(make_tar({
            "demo/composer.json": '{"require":{"laravel/framework":"12"}}',
            "demo/artisan": "#!/usr/bin/env php\n",
            "demo/package.json": json.dumps({
                "scripts": {"build": "vite build"},
                "dependencies": {"vite": "7.0.0", "laravel-vite-plugin": "1.0.0"},
            }),
            "demo/package-lock.json": "{}",
            "demo/vite.config.js": "export default {}",
        }))
        self.assertEqual(model.flattened_wrapper, "demo")
        self.assertEqual(model.application_root, ".")
        self.assertEqual(model.frontend_root, ".")
        self.assertEqual(model.frontends[0].kind, "vite")
        self.assertEqual(model.frontends[0].package_manager, "npm")
        self.assertEqual(model.frontends[0].build_output, "public/build")

    def test_build_project_model_from_tree_records_explicit_wrapper_and_uses_tree_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "composer.json").write_text('{"require":{"laravel/framework":"12"}}', encoding="utf-8")
            (root / "artisan").write_text("#!/usr/bin/env php\n", encoding="utf-8")
            (root / "package.json").write_text(
                json.dumps({"scripts": {"build": "vite build"}, "dependencies": {"vite": "7.0.0", "laravel-vite-plugin": "1.0.0"}}),
                encoding="utf-8",
            )
            (root / "package-lock.json").write_text("{}", encoding="utf-8")
            index = {
                "composer.json": str(root / "composer.json"),
                "artisan": str(root / "artisan"),
                "package.json": str(root / "package.json"),
                "package-lock.json": str(root / "package-lock.json"),
            }
            model = build_project_model_from_tree(index, wrapper="repo-hash")
        self.assertEqual(model.flattened_wrapper, "repo-hash")
        self.assertEqual(model.frontend_root, ".")
        self.assertEqual(model.frontends[0].build_output, "public/build")

    def test_project_root_serialization_keeps_security_relevant_evidence(self):
        root = ProjectRoot(
            kind="vite",
            root="frontend",
            confidence=0.8,
            evidence={"package_json_path": "frontend/package.json", "has_package_lock": True},
            package_manager="npm",
            build_script="build",
            build_output="frontend/dist",
        )
        self.assertEqual(root.kind, "vite")
        self.assertEqual(root.root, "frontend")
        self.assertEqual(root.evidence["package_json_path"], "frontend/package.json")


if __name__ == "__main__":
    unittest.main()
