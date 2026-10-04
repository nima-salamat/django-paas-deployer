"""Strong contract tests for deployment entrypoint detection and runtime paths."""

from __future__ import annotations

import ast
import io
import tarfile
import unittest

from deployments.common.exceptions import DeploymentValidationError


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


class EntrypointRuntimeContractTests(unittest.TestCase):
    def test_entrypoint_module_has_one_definition_per_public_resolver(self):
        from pathlib import Path
        import deployments.core.entrypoints as entrypoints

        source = Path(entrypoints.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for name in (
            "resolve_fastapi_entrypoint",
            "resolve_flask_entrypoint",
            "resolve_python_entrypoint",
            "resolve_node_entrypoint",
            "check_requirements_txt",
            "check_package_json",
        ):
            self.assertEqual(names.count(name), 1, name)

    def test_fastapi_pyproject_entrypoint_is_authoritative_and_normalized(self):
        from deployments.core.entrypoints import resolve_fastapi_entrypoint

        result = resolve_fastapi_entrypoint(make_tar({
            "my-api/src/app/__init__.py": "",
            "my-api/src/app/main.py": "from fastapi import FastAPI\napplication = FastAPI()\n",
            "my-api/pyproject.toml": '[tool.fastapi]\nentrypoint = "my-api.src.app.main:application"\n',
        }))

        self.assertTrue(result["detected"])
        self.assertEqual(result["module"], "app.main")
        self.assertEqual(result["callable"], "application")
        self.assertEqual(result["entrypoint"], "app.main:application")
        self.assertEqual(result["source_root"], "src")
        self.assertEqual(result["working_directory"], "/app/src")

    def test_fastapi_source_scan_prefers_main_app_over_other_candidates(self):
        from deployments.core.entrypoints import resolve_fastapi_entrypoint

        result = resolve_fastapi_entrypoint(make_tar({
            "main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "server.py": "from fastapi import FastAPI\napplication = FastAPI()\n",
            "service.py": "from fastapi import FastAPI\napi = FastAPI()\n",
        }))
        self.assertEqual(result["entrypoint"], "main:app")

    def test_fastapi_source_scan_skips_tests_migrations_and_cached_files(self):
        from deployments.core.entrypoints import resolve_fastapi_entrypoint

        result = resolve_fastapi_entrypoint(make_tar({
            "tests/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "migrations/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "__pycache__/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "main.py": "from fastapi import FastAPI\napplication = FastAPI()\n",
        }))
        self.assertEqual(result["entrypoint"], "main:application")

    def test_fastapi_requires_actual_app_assignment(self):
        from deployments.core.entrypoints import resolve_fastapi_entrypoint

        result = resolve_fastapi_entrypoint(make_tar({
            "main.py": "from fastapi import FastAPI\nrouter_factory = FastAPI\n",
        }))
        self.assertFalse(result["detected"])
        self.assertIsNone(result["module"])
        self.assertIsNone(result["callable"])

    def test_fastapi_pyproject_invalid_target_falls_back_to_source_scan(self):
        from deployments.core.entrypoints import resolve_fastapi_entrypoint

        result = resolve_fastapi_entrypoint(make_tar({
            "pyproject.toml": '[tool.fastapi]\nentrypoint = "not a target"\n',
            "app.py": "from fastapi import FastAPI\napp = FastAPI()\n",
        }))
        self.assertEqual(result["entrypoint"], "app:app")
        self.assertEqual(result["source"], "source_scan")

    def test_fastapi_empty_archive_returns_not_detected_without_mutating_stream(self):
        from deployments.core.entrypoints import resolve_fastapi_entrypoint

        stream = make_tar({})
        result = resolve_fastapi_entrypoint(stream)
        self.assertFalse(result["detected"])
        self.assertEqual(stream.tell(), 0)

    def test_python_runtime_context_handles_root_src_and_nested_backend_src(self):
        from deployments.core.entrypoints import resolve_python_runtime_context

        cases = (
            (
                {"app/__init__.py", "app/main.py"},
                "app.main",
                {"module": "app.main", "source_root": "", "working_directory": "/app"},
            ),
            (
                {"src/app/__init__.py", "src/app/main.py"},
                "src.app.main",
                {"module": "app.main", "source_root": "src", "working_directory": "/app/src"},
            ),
            (
                {"backend/src/app/__init__.py", "backend/src/app/main.py"},
                "app.main",
                {"module": "app.main", "source_root": "backend/src", "working_directory": "/app/backend/src"},
            ),
        )
        for names, module, expected in cases:
            with self.subTest(names=names, module=module):
                self.assertEqual(resolve_python_runtime_context(names, module), expected)

    def test_python_runtime_context_flattens_single_archive_wrapper(self):
        from deployments.core.entrypoints import resolve_python_runtime_context

        result = resolve_python_runtime_context(
            {
                "release-abc/src/app/__init__.py",
                "release-abc/src/app/main.py",
            },
            "release-abc.src.app.main",
        )
        self.assertEqual(result["module"], "app.main")
        self.assertEqual(result["source_root"], "src")
        self.assertEqual(result["working_directory"], "/app/src")

    def test_python_runtime_context_does_not_guess_missing_source_root(self):
        from deployments.core.entrypoints import resolve_python_runtime_context

        result = resolve_python_runtime_context(
            {"README.md", "src/not_the_target.py"},
            "app.main",
        )
        self.assertEqual(result["module"], "app.main")
        self.assertEqual(result["source_root"], "")
        self.assertEqual(result["working_directory"], "/app")

    def test_django_asgi_and_wsgi_detection_are_distinct(self):
        from deployments.core.entrypoints import resolve_django_entrypoint

        asgi = resolve_django_entrypoint(make_tar({
            "manage.py": 'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")\n',
            "config/settings.py": 'ASGI_APPLICATION = "config.asgi.application"\n',
        }))
        wsgi = resolve_django_entrypoint(make_tar({
            "manage.py": 'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")\n',
            "config/settings.py": 'WSGI_APPLICATION = "config.wsgi.application"\n',
        }))
        self.assertEqual(asgi, {"type": "asgi", "module": "config.asgi", "override": False})
        self.assertEqual(wsgi, {"type": "wsgi", "module": "config.wsgi", "override": False})

    def test_django_server_type_override_changes_type_but_not_module(self):
        from deployments.core.entrypoints import resolve_django_entrypoint

        result = resolve_django_entrypoint(
            make_tar({
                "manage.py": 'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")\n',
                "config/settings.py": 'ASGI_APPLICATION = "config.asgi.application"\n',
            }),
            server_type="wsgi",
        )
        self.assertEqual(result["type"], "wsgi")
        self.assertEqual(result["module"], "config.asgi")
        self.assertTrue(result["override"])

    def test_django_rejects_invalid_server_type_before_source_scan(self):
        from deployments.core.entrypoints import resolve_django_entrypoint

        with self.assertRaises(DeploymentValidationError) as ctx:
            resolve_django_entrypoint(make_tar({}), server_type="garbage")
        self.assertEqual(ctx.exception.stage, "entrypoint_detection")
        self.assertIn("server_type", str(ctx.exception))

    def test_django_missing_entrypoint_is_a_deployment_validation_error(self):
        from deployments.core.entrypoints import require_django_entrypoint

        with self.assertRaises(DeploymentValidationError) as ctx:
            require_django_entrypoint(make_tar({
                "manage.py": 'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")\n',
                "config/settings.py": "SECRET_KEY = 'x'\n",
            }))
        self.assertEqual(ctx.exception.stage, "entrypoint_detection")

    def test_flask_detection_supports_factory_and_asgi(self):
        from deployments.core.entrypoints import resolve_flask_entrypoint

        flask = resolve_flask_entrypoint(make_tar({
            "app.py": "from flask import Flask\napp = Flask(__name__)\n",
        }))
        factory = resolve_flask_entrypoint(make_tar({
            "app.py": "from flask import Flask\ndef create_app():\n    return Flask(__name__)\n",
        }))
        asgi = resolve_flask_entrypoint(make_tar({
            "app.py": "from fastapi import FastAPI\napp = FastAPI()\n",
        }))
        self.assertEqual((flask["type"], flask["callable"]), ("wsgi", "app"))
        self.assertEqual(factory["callable"], "create_app()")
        self.assertEqual(asgi["type"], "asgi")

    def test_node_detection_extracts_start_main_build_and_framework(self):
        from deployments.core.entrypoints import resolve_node_entrypoint

        result = resolve_node_entrypoint(make_tar({
            "package.json": (
                '{"main":"server.js","scripts":{"start":"node server.js","build":"vite build"},'
                '"dependencies":{"vite":"7.0.0"}}'
            ),
        }))
        self.assertEqual(result["start_script"], "node server.js")
        self.assertEqual(result["main"], "server.js")
        self.assertTrue(result["has_build"])
        self.assertEqual(result["framework"], "vite")

    def test_node_framework_detection_uses_dependency_priority(self):
        from deployments.core.entrypoints import _detect_node_framework

        self.assertEqual(_detect_node_framework({"dependencies": {"next": "1"}}), "nextjs")
        self.assertEqual(_detect_node_framework({"dependencies": {"react": "1", "vite": "1"}}), "react")
        self.assertEqual(_detect_node_framework({"dependencies": {"fastify": "1"}}), "fastify")
        self.assertEqual(_detect_node_framework({"dependencies": {}}), "node")

    def test_python_dependency_manifest_accepts_requirements_pyproject_and_pipfile(self):
        from deployments.core.entrypoints import check_requirements_txt

        for manifest in ("requirements.txt", "pyproject.toml", "Pipfile"):
            with self.subTest(manifest=manifest):
                check_requirements_txt(
                    make_tar({manifest: "fastapi\n"}),
                    platform="fastapi",
                )

    def test_python_dependency_manifest_rejects_missing_manifest(self):
        from deployments.core.entrypoints import check_requirements_txt

        with self.assertRaises(DeploymentValidationError) as ctx:
            check_requirements_txt(make_tar({"main.py": ""}), platform="fastapi")
        self.assertEqual(ctx.exception.stage, "requirements_check")
        self.assertIn("requirements.txt", str(ctx.exception))

    def test_package_json_check_is_platform_scoped(self):
        from deployments.core.entrypoints import check_package_json

        check_package_json(make_tar({}), platform="python")
        with self.assertRaises(DeploymentValidationError):
            check_package_json(make_tar({}), platform="react")

    def test_all_entrypoint_resolvers_reset_tar_stream_position(self):
        from deployments.core.entrypoints import (
            resolve_fastapi_entrypoint,
            resolve_flask_entrypoint,
            resolve_node_entrypoint,
        )

        factories = (
            resolve_fastapi_entrypoint,
            resolve_flask_entrypoint,
            resolve_node_entrypoint,
        )
        for resolver in factories:
            stream = make_tar({"main.py": "from fastapi import FastAPI\napp = FastAPI()\n", "package.json": "{}"})
            stream.seek(7)
            resolver(stream)
            self.assertEqual(stream.tell(), 0, resolver.__name__)


if __name__ == "__main__":
    unittest.main()
