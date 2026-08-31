"""
Regression tests for the four issues fixed in this patch:

1. Public docs endpoints must remain accessible to anonymous clients
   (and to clients that send an expired/invalid Authorization header).
2. The ``Deploy`` facade constructor must accept a ``frontend`` kwarg
   and forward it to ``DeploymentConfig.frontend`` (this was the root
   cause of the ``Deploy.__init__() got an unexpected keyword argument
   'frontend'`` error reported during Laravel deploys).
3. ``validate_tenant_config`` must surface friendly warnings for
   unknown / blocked tenant config keys without ever raising.
4. ``_inject_laravel_frontend_build`` must prepend a
   ``npm config set registry <mirror>`` (or pnpm / yarn equivalent)
   line when the operator has configured a non-default ``mirror.npm``,
   and must NOT emit it when the registry equals the public default.
"""

from __future__ import annotations

import io
import os
import sys
import tarfile
import types
import unittest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_tar(files: dict[str, str]) -> io.BytesIO:
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w") as tar:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    bio.seek(0)
    return bio


def load_dockerfile_module():
    """Load the dockerfile module with a stubbed settings service so the
    npm-registry mirror resolution can be tested without Django.

    Always (re)installs the ``core.settings_service`` stub so a previous
    test that imported the real settings_service module cannot poison
    these tests. The stub is installed on BOTH ``sys.modules`` AND the
    ``core`` package's ``settings_service`` attribute — the latter is what
    ``from core import settings_service`` actually resolves to.
    """
    # Ensure the core.global_settings.config module is importable.
    # The Deploy facade (deployments/core/deploy.py) imports
    # ``from core.global_settings.config import PlanTypeChoices`` — so the
    # stub MUST expose PlanTypeChoices (any object is fine; it's only used
    # for ``str(self.platform_type) == str(PlanTypeChoices.APP)`` checks).
    mod = types.ModuleType("core.global_settings.config")
    mod.MIRROR_DOCKER = "mirror.test"
    mod.PLATFORM_CHOICES = []
    mod.default_ports = {}
    mod.DEFAULT_EXPOSE_PORT = 80
    mod.DEFAULT_RUNTIME_VERSIONS = {}
    mod.Config = types.SimpleNamespace()
    # Minimal PlanTypeChoices stub — used by Deploy._network_specs() for an
    # APP-type branch only.
    class _PTC:
        DB = "DB"
        APP = "APP"
        READY = "READY"
    mod.PlanTypeChoices = _PTC
    sys.modules["core.global_settings.config"] = mod
    pkg = types.ModuleType("core.global_settings")
    pkg.__path__ = []
    sys.modules["core.global_settings"] = pkg
    if "core" not in sys.modules:
        core_pkg = types.ModuleType("core")
        core_pkg.__path__ = []
        sys.modules["core"] = core_pkg
    core_pkg = sys.modules["core"]

    # ALWAYS install the stub so we control the npm registry value here.
    svc = types.ModuleType("core.settings_service")
    svc._npm_registry = "https://registry.npmjs.org"
    def mirror_npm() -> str:
        return svc._npm_registry
    def mirror_docker() -> str:
        return "mirror.test"
    def mirror_python() -> str:
        return "https://pypi.org/simple"
    def mirror_composer() -> str:
        return ""
    def mirror_apt() -> str:
        return ""
    def mirror_go() -> str:
        return ""
    def get_str(key, default=""):
        if key == "mirror.npm":
            return svc._npm_registry
        return default
    svc.mirror_npm = mirror_npm
    svc.mirror_docker = mirror_docker
    svc.mirror_python = mirror_python
    svc.mirror_composer = mirror_composer
    svc.mirror_apt = mirror_apt
    svc.mirror_go = mirror_go
    svc.get_str = get_str
    sys.modules["core.settings_service"] = svc
    # The critical line: also set the package attribute so
    # ``from core import settings_service`` picks up the stub. Without
    # this, a previous test that imported the real settings_service.py
    # would leave the real module attached to the package attribute and
    # our sys.modules entry would be ignored.
    core_pkg.settings_service = svc

    # Drop any cached ``deployments.core.dockerfile`` so it re-imports and
    # picks up the new stub.
    sys.modules.pop("deployments.core.dockerfile", None)
    from deployments.core import dockerfile
    return dockerfile


# ---------------------------------------------------------------------------
# Issue 1 — public docs endpoints have empty authentication_classes
# ---------------------------------------------------------------------------


class DocsPublicAuthTests(unittest.TestCase):
    """We assert by reading the source file instead of importing ``docs.apis``.

    Importing ``docs.apis`` triggers Django model loading (``docs/models.py``
    defines Django models) which requires the full project settings. Reading
    the source file gives the same guarantees without needing the full app
    registry.
    """

    @classmethod
    def setUpClass(cls):
        from pathlib import Path
        cls.source = Path(__file__).parents[2].joinpath("docs", "apis.py").read_text()

    def test_public_views_disable_jwt_authentication(self):
        # Each public view class must set authentication_classes = [] (or
        # the shared _PUBLIC_AUTH = [] alias) so a stale Bearer token in the
        # Authorization header cannot 401-block anonymous reads.
        for class_name in (
            "PublicDocumentsAPIView",
            "PublicCategoryTreeAPIView",
            "PublicDocumentDetailAPIView",
            "DocumentAssetAPIView",
        ):
            # Find the class block and verify the _PUBLIC_AUTH alias or
            # authentication_classes = [] is set on it (or globally above).
            self.assertIn(class_name, self.source,
                          msg=f"{class_name} must still exist in docs/apis.py")
            # The whole module shares _PUBLIC_AUTH and assigns it to all four
            # public views. Assert the alias is defined and used.
        self.assertIn("_PUBLIC_AUTH = []", self.source,
                      msg="docs/apis.py must define _PUBLIC_AUTH = [] so public "
                          "views never go through JWTAuthentication.")
        # Count how many views wire authentication_classes = _PUBLIC_AUTH.
        self.assertGreaterEqual(
            self.source.count("authentication_classes = _PUBLIC_AUTH"), 4,
            msg="All four public docs views (PublicDocumentsAPIView, "
                "PublicCategoryTreeAPIView, PublicDocumentDetailAPIView, "
                "DocumentAssetAPIView) must set authentication_classes = _PUBLIC_AUTH.",
        )

    def test_public_views_allow_anonymous(self):
        # Public AllowAny permission_classes on the three read-only views.
        self.assertIn("permission_classes = [AllowAny]", self.source)
        # And the public views don't accidentally set IsAuthenticated.
        # Find the slice for the public classes and check.
        for class_name in (
            "PublicDocumentsAPIView",
            "PublicCategoryTreeAPIView",
            "PublicDocumentDetailAPIView",
        ):
            block = self.source.split(f"class {class_name}", 1)[1]
            block = block.split("class ", 1)[0]
            self.assertIn("AllowAny", block,
                          msg=f"{class_name} must use AllowAny permission.")


# ---------------------------------------------------------------------------
# Issue 2 — Deploy facade accepts and forwards `frontend` kwarg
# ---------------------------------------------------------------------------


class DeployFacadeFrontendKwargTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Install the proper stub BEFORE the test method imports the
        # ``deployments.core.deploy`` module. The existing
        # ``test_frontend_build_regressions.load_dockerfile_module``
        # installs a bare stub without ``PlanTypeChoices``, so we need to
        # replace it here.
        load_dockerfile_module()

    def test_deploy_init_accepts_frontend_kwarg(self):
        """Reproduces the reported crash and verifies the fix.

        Before the fix, calling ``Deploy(..., frontend={...})`` raised
        ``TypeError: Deploy.__init__() got an unexpected keyword argument
        'frontend'``. After the fix, the kwarg is accepted and forwarded
        to ``DeploymentConfig.frontend`` by ``_config()``.
        """
        # The Deploy facade imports docker; if the docker package is not
        # installed in the test environment, skip — we cannot construct a
        # real facade object then.
        try:
            import docker  # noqa: F401
        except ImportError:
            self.skipTest("docker SDK not installed")

        from deployments.core.deploy import Deploy, _sanitize_frontend_dict

        # Direct reproduction of the user's crash.
        deploy = Deploy(
            name="test-app",
            tag="v1",
            zip_filename="/tmp/test.zip",
            dockerfile_text="FROM alpine",
            max_cpu=1,
            max_ram=512,
            networks=[],
            volumes=[],
            port=80,
            read_only=False,
            platform="laravel",
            platform_type="APP",
            frontend={"npm_registry": "https://npm.test/"},
        )
        self.assertEqual(deploy.frontend, {"npm_registry": "https://npm.test/"})

        # The frontend dict must be plumbed all the way into the
        # DeploymentConfig that the orchestrator receives.
        cfg = deploy._config()
        self.assertEqual(cfg.frontend, {"npm_registry": "https://npm.test/"})

    def test_sanitize_frontend_dict_drops_non_dict_input(self):
        from deployments.core.deploy import _sanitize_frontend_dict
        # Non-dict input becomes an empty dict.
        self.assertEqual(_sanitize_frontend_dict(None), {})
        self.assertEqual(_sanitize_frontend_dict("frontend"), {})
        self.assertEqual(_sanitize_frontend_dict(123), {})
        # Dict input is filtered to string keys + primitive values.
        self.assertEqual(
            _sanitize_frontend_dict({
                "npm_registry": "https://npm.test/",
                "package_manager": "pnpm",
                "skip_int": 1,  # bool/int/float/str/None are kept
                "skip_bool": True,
                "skip_none": None,
                123: "dropped",  # non-string key dropped
                "shell_payload": "rm -rf /",  # kept (validated later)
                "nested": {"a": "b", "c": 1, "d": ["x"]},
                "nested_bad": {"a": ["x"]},  # filtered to {"a":?} — drop list values
            }),
            {
                "npm_registry": "https://npm.test/",
                "package_manager": "pnpm",
                "skip_int": 1,
                "skip_bool": True,
                "skip_none": None,
                "shell_payload": "rm -rf /",
                "nested": {"a": "b", "c": 1},
            },
        )


# ---------------------------------------------------------------------------
# Issue 3 — validate_tenant_config surfaces friendly warnings
# ---------------------------------------------------------------------------


class TenantConfigContractTests(unittest.TestCase):
    def test_known_keys_are_silent(self):
        from deployments.common.config import validate_tenant_config
        cfg = {
            "platform": "laravel",
            "env": {"APP_ENV": "production", "DB_CONNECTION": "sqlite"},
        }
        report = validate_tenant_config(cfg)
        self.assertEqual(report["warnings"], [])
        self.assertEqual(sorted(report["known_keys"]), ["env", "platform"])
        self.assertEqual(report["unknown_keys"], [])
        self.assertEqual(report["blocked_stripped"], [])

    def test_unknown_key_warns_with_suggestion(self):
        from deployments.common.config import validate_tenant_config
        # "environment" is a known alias → suggested as "env".
        cfg = {"environment": {"APP_ENV": "production"}}
        report = validate_tenant_config(cfg)
        # "environment" is technically a known key (alias entry), so we
        # check that the alias mapping handles it. The contract lists both
        # "env" and "environment", so "environment" is a known key.
        self.assertIn("environment", report["known_keys"])
        # Now use a real typo: "envir" (Levenshtein distance 2 from "env").
        cfg = {"envir": {"APP_ENV": "production"}}
        report = validate_tenant_config(cfg)
        self.assertIn("envir", report["unknown_keys"])
        self.assertTrue(any("did you mean 'env'" in w for w in report["warnings"]))

    def test_blocked_keys_are_flagged(self):
        from deployments.common.config import validate_tenant_config
        cfg = {
            "platform": "laravel",
            "worker_count": 4,        # blocked — operator-only
            "volumes": ["x"],         # blocked
        }
        report = validate_tenant_config(cfg)
        self.assertIn("worker_count", report["blocked_stripped"])
        self.assertIn("volumes", report["blocked_stripped"])
        self.assertTrue(
            any("worker_count" in w and "stripped" in w for w in report["warnings"])
        )

    def test_never_raises_on_garbage_input(self):
        from deployments.common.config import validate_tenant_config
        # None, empty, string, list, etc. must never raise.
        for raw in (None, "", "not a dict", 123, [1, 2, 3], {"x": "y"}, {"env": "not a dict"}):
            report = validate_tenant_config(raw)
            self.assertIsInstance(report, dict)
            self.assertIn("warnings", report)
            self.assertIn("contract", report)

    def test_sanitize_strips_blocked_keys(self):
        from deployments.common.config import sanitize_tenant_config
        out = sanitize_tenant_config({
            "platform": "laravel",
            "worker_count": 4,        # stripped
            "build_options": {"target": "prod", "no_cache": True, "evil": "rm -rf /"},
        })
        self.assertNotIn("worker_count", out)
        self.assertEqual(out["build_options"], {"target": "prod", "no_cache": True})
        self.assertEqual(out["platform"], "laravel")


# ---------------------------------------------------------------------------
# Issue 4 — npm mirror is injected into the Laravel frontend build step
# ---------------------------------------------------------------------------


class LaravelFrontendNpmMirrorTests(unittest.TestCase):
    def setUp(self):
        # Load the module fresh — this re-installs the core.settings_service
        # stub and resets _npm_registry to the public default.
        self.d = load_dockerfile_module()
        # Default: use the public registry; tests can override.
        sys.modules["core.settings_service"]._npm_registry = "https://registry.npmjs.org"

    def _config(self, **overrides):
        class Config:
            environment = overrides.get("environment", {})
            frontend = overrides.get("frontend", {})
            package_manager = overrides.get("package_manager", "npm")
            install_command = overrides.get("install_command", "composer install --no-dev --optimize-autoloader")
            build_command = overrides.get("build_command", "npm run build")
            runtime_version = overrides.get("runtime_version", None)
            build_options = overrides.get("build_options", {})
        return Config()

    def _pkg_tar(self):
        return make_tar({
            "composer.json": '{"require":{"laravel/framework":"^12.0"}}',
            "artisan": "<?php",
            "package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7","react":"19"}}',
            "package-lock.json": "{}",
        })

    def test_default_registry_emits_no_config_set_line(self):
        # Default registry => no `npm config set registry` line.
        sys.modules["core.settings_service"]._npm_registry = "https://registry.npmjs.org"
        out = self.d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=self._pkg_tar(),
            config=self._config(),
            logger=None,
        )
        block = out.split("# --- Laravel frontend build (injected) ---", 1)[1]
        self.assertIn("npm ci", block)
        self.assertIn("npm run build", block)
        self.assertNotIn("npm config set registry", block)

    def test_operator_mirror_is_injected(self):
        # Operator configured mirror.npm to a non-default value => the
        # `npm config set registry <mirror>` line is added before install.
        sys.modules["core.settings_service"]._npm_registry = "https://npm.ir/mirror/"
        out = self.d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=self._pkg_tar(),
            config=self._config(),
            logger=None,
        )
        block = out.split("# --- Laravel frontend build (injected) ---", 1)[1]
        self.assertIn("npm config set registry https://npm.ir/mirror/", block)
        self.assertIn("npm ci", block)
        self.assertIn("npm run build", block)

    def test_tenant_frontend_npm_registry_overrides_operator_mirror(self):
        # If the tenant explicitly sets frontend.npm_registry, it wins.
        sys.modules["core.settings_service"]._npm_registry = "https://operator/mirror/"
        out = self.d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=self._pkg_tar(),
            config=self._config(frontend={"npm_registry": "https://tenant/mirror/"}),
            logger=None,
        )
        block = out.split("# --- Laravel frontend build (injected) ---", 1)[1]
        self.assertIn("npm config set registry https://tenant/mirror/", block)
        self.assertNotIn("https://operator/mirror/", block)

    def test_pnpm_uses_pnpm_config_set(self):
        sys.modules["core.settings_service"]._npm_registry = "https://npm.ir/mirror/"
        # Provide pnpm-lock so detection picks pnpm.
        tar = make_tar({
            "composer.json": '{"require":{"laravel/framework":"^12.0"}}',
            "artisan": "<?php",
            "package.json": '{"packageManager":"pnpm@10.0.0","scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
            "pnpm-lock.yaml": "lockfileVersion: '9'\n",
        })
        out = self.d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=tar,
            config=self._config(package_manager="pnpm"),
            logger=None,
        )
        block = out.split("# --- Laravel frontend build (injected) ---", 1)[1]
        self.assertIn("pnpm config set registry https://npm.ir/mirror/", block)
        self.assertIn("pnpm install --frozen-lockfile", block)

    def test_yarn_uses_yarn_config_set(self):
        sys.modules["core.settings_service"]._npm_registry = "https://npm.ir/mirror/"
        # Detection of yarn requires a yarn.lock file in the tar.
        tar = make_tar({
            "composer.json": '{"require":{"laravel/framework":"^12.0"}}',
            "artisan": "<?php",
            "package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7"}}',
            "yarn.lock": '# THIS IS AN AUTOGENERATED FILE\n',
        })
        out = self.d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=tar,
            config=self._config(),
            logger=None,
        )
        block = out.split("# --- Laravel frontend build (injected) ---", 1)[1]
        self.assertIn("yarn config set registry https://npm.ir/mirror/", block)
        self.assertIn("yarn install --frozen-lockfile", block)

    def test_dockerfile_remains_well_formed_with_registry_line(self):
        # The block must end with a line that has no trailing backslash,
        # otherwise the Dockerfile parser keeps waiting for the next line.
        sys.modules["core.settings_service"]._npm_registry = "https://npm.ir/mirror/"
        out = self.d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=self._pkg_tar(),
            config=self._config(),
            logger=None,
        )
        block = out.split("# --- Laravel frontend build (injected) ---", 1)[1]
        # Drop the EXPOSE 80 line that follows the block.
        block_only = block.split("EXPOSE 80", 1)[0]
        last_line = [ln for ln in block_only.rstrip().splitlines() if ln.strip()][-1]
        self.assertFalse(
            last_line.rstrip().endswith("\\"),
            msg=f"Last RUN line of the injected block must not end with a "
                f"backslash continuation. Got: {last_line!r}",
        )


# ---------------------------------------------------------------------------
# Issue 5 (auditability) — frontend detection + resolution emit log lines
# ---------------------------------------------------------------------------


class _RecordingLogger:
    """Tiny test double matching DeploymentLogger.info/.warning signatures."""

    def __init__(self):
        self.entries: list[dict] = []

    def info(self, stage, message, *, progress=None, details=None):
        self.entries.append({
            "level": "info", "stage": stage, "message": message,
            "progress": progress, "details": details or {},
        })

    def warning(self, stage, message, *, progress=None, details=None):
        self.entries.append({
            "level": "warning", "stage": stage, "message": message,
            "progress": progress, "details": details or {},
        })

    def error(self, stage, message, *, progress=None, details=None):
        self.entries.append({
            "level": "error", "stage": stage, "message": message,
            "progress": progress, "details": details or {},
        })


class LaravelDockerfileRootRegressionTests(unittest.TestCase):
    def setUp(self):
        self.d = load_dockerfile_module()
        sys.modules["core.settings_service"]._npm_registry = "https://package-mirror.liara.ir/repository/npm/"

    def _config(self, **overrides):
        class Config:
            environment = overrides.get("environment", {})
            frontend = overrides.get("frontend", {})
            package_manager = overrides.get("package_manager", None)
            install_command = overrides.get("install_command", None)
            build_command = overrides.get("build_command", None)
            runtime_version = overrides.get("runtime_version", None)
            build_options = overrides.get("build_options", {})
            document_root = overrides.get("document_root", None)
            php_version = overrides.get("php_version", None)
            server_type = None
            entry_point = None
            celery = False
            celery_beat = False
            worker_count = 1
            port = 80
            project_model = None
            platform = "laravel"
        return Config()

    def _tar(self):
        return make_tar({
            "composer.json": '{"require":{"php":"^8.4","laravel/framework":"^13.0"}}',
            "artisan": "<?php",
            "public/index.php": "<?php",
            "package.json": '{"scripts":{"dev":"vite","build":"vite build"},"devDependencies":{"vite":"^8.0.16","laravel-vite-plugin":"^3.0.0"}}',
            "package-lock.json": "{}",
            "yarn.lock": "# yarn lockfile",
            "vite.config.js": "export default {}",
        })

    def _template(self):
        return """FROM mirror.test/php:8.4-apache
ENV APACHE_DOCUMENT_ROOT=/var/www/html/public
WORKDIR /var/www/html
COPY . /var/www/html/
# --- Laravel template composer install (app-root aware) ---
RUN cd __LARAVEL_APP_ROOT__\\
    && test -f composer.json \\
    && if [ -n "https://package-mirror.liara.ir/repository/composer/" ]; then \\
         composer config -g repo.packagist composer https://package-mirror.liara.ir/repository/composer/; \\
         composer config -g secure-http false; \\
       fi \\
    && composer install --no-dev --prefer-dist --no-interaction --no-progress --optimize-autoloader --no-scripts \\
    && test -f vendor/autoload.php

RUN cd __LARAVEL_APP_ROOT__\\
    && mkdir -p storage/framework/cache storage/framework/sessions storage/framework/views storage/logs bootstrap/cache \\
    && php artisan package:discover --ansi || true \\
    && echo "Laravel composer install OK"

EXPOSE 80
CMD ["apache2-foreground"]
"""

    def test_no_unresolved_laravel_root_and_frontend_is_built(self):
        out = self.d._render_php(self._template(), self._tar(), self._config(), None)
        self.assertNotIn("__LARAVEL_APP_ROOT__", out)
        self.assertIn("# --- Laravel frontend build (injected) ---", out)
        self.assertIn("# front_build_platform=vite", out)
        self.assertIn("npm config set registry https://package-mirror.liara.ir/repository/npm/", out)
        self.assertIn("npm ci", out)
        self.assertIn("npm run build", out)
        self.assertNotIn("# --- Laravel template composer install (app-root aware) ---", out)

    def test_frontend_is_auto_detected_without_frontend_config(self):
        out = self.d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=self._tar(),
            config=self._config(frontend={}),
            logger=None,
        )
        self.assertIn("# front_build_platform=vite", out)
        self.assertIn("npm ci", out)
        self.assertIn("npm run build", out)


class LaravelFrontendDetectionAuditTests(unittest.TestCase):
    def setUp(self):
        self.d = load_dockerfile_module()
        sys.modules["core.settings_service"]._npm_registry = "https://registry.npmjs.org"

    def _config(self, **overrides):
        class Config:
            environment = overrides.get("environment", {})
            frontend = overrides.get("frontend", {})
            package_manager = overrides.get("package_manager", "npm")
            install_command = overrides.get("install_command", "composer install --no-dev --optimize-autoloader")
            build_command = overrides.get("build_command", "npm run build")
            runtime_version = overrides.get("runtime_version", None)
            build_options = overrides.get("build_options", {})
        return Config()

    def _pkg_tar(self):
        return make_tar({
            "composer.json": '{"require":{"laravel/framework":"^12.0"}}',
            "artisan": "<?php",
            "package.json": '{"scripts":{"build":"vite build"},"devDependencies":{"vite":"7","react":"19"}}',
            "package-lock.json": "{}",
        })

    def _no_pkg_tar(self):
        # No package.json — backend-only Laravel app.
        return make_tar({
            "composer.json": '{"require":{"laravel/framework":"^12.0"}}',
            "artisan": "<?php",
        })

    def test_detection_log_is_emitted_when_package_json_exists(self):
        log = _RecordingLogger()
        self.d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=self._pkg_tar(),
            config=self._config(),
            logger=log,
        )
        # Detection log MUST be emitted at progress=15.
        detect = [e for e in log.entries if e["stage"] == "frontend_detection"]
        self.assertTrue(detect,
                        msg="Detection must emit a 'frontend_detection' log line "
                            "even when the user did not supply a frontend config.")
        first = detect[0]
        self.assertEqual(first["level"], "info")
        self.assertIn("kind='vite'", first["message"],
                      msg="Detection log must report the resolved kind, e.g. 'vite'.")
        self.assertEqual(first["details"].get("package_manager"), "npm")
        self.assertEqual(first["details"].get("has_package_json"), True)
        self.assertIn("package.json", first["details"].get("detected_files", []))

    def test_detection_log_is_emitted_when_no_package_json(self):
        log = _RecordingLogger()
        out = self.d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=self._no_pkg_tar(),
            config=self._config(),
            logger=log,
        )
        # No frontend block in the Dockerfile.
        self.assertNotIn("# --- Laravel frontend build (injected) ---", out)
        # But a detection log line MUST still be emitted so the user can
        # verify the platform actually looked for a package.json.
        detect = [e for e in log.entries if e["stage"] == "frontend_detection"]
        self.assertTrue(detect,
                        msg="Detection must still emit a log line when no "
                            "package.json is found, so the user can verify "
                            "the platform attempted detection.")
        self.assertIn("No package.json", detect[0]["message"])
        self.assertEqual(detect[0]["details"].get("reason"), "no_package_json")

    def test_resolution_log_reports_source_user_vs_auto(self):
        log = _RecordingLogger()
        # User explicitly sets front_build_platform via env override.
        self.d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=self._pkg_tar(),
            config=self._config(environment={"FRONT_BUILD_PLATFORM": "react"}),
            logger=log,
        )
        # A 'frontend_resolution' log line MUST be present.
        resolution = [e for e in log.entries if e["stage"] == "frontend_resolution"]
        self.assertTrue(resolution,
                        msg="Resolution must emit a 'frontend_resolution' log line.")
        first = resolution[0]
        self.assertEqual(first["details"].get("kind_source"), "env",
                         msg="When FRONT_BUILD_PLATFORM is set in env, "
                             "kind_source must be 'env'.")
        self.assertEqual(first["details"].get("kind"), "react")

    def test_resolution_log_reports_source_user_override(self):
        log = _RecordingLogger()
        # User sets frontend.kind = "mix" explicitly.
        self.d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=self._pkg_tar(),
            config=self._config(frontend={"kind": "mix"}),
            logger=log,
        )
        resolution = [e for e in log.entries if e["stage"] == "frontend_resolution"]
        self.assertTrue(resolution)
        self.assertEqual(resolution[0]["details"].get("kind_source"), "user_override")
        self.assertEqual(resolution[0]["details"].get("kind"), "mix")

    def test_resolution_log_reports_source_auto(self):
        log = _RecordingLogger()
        # No user config — auto-detect must take over.
        self.d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=self._pkg_tar(),
            config=self._config(),
            logger=log,
        )
        resolution = [e for e in log.entries if e["stage"] == "frontend_resolution"]
        self.assertTrue(resolution)
        self.assertEqual(resolution[0]["details"].get("kind_source"), "auto")
        self.assertEqual(resolution[0]["details"].get("kind"), "vite")

    def test_dockerfile_generation_log_reports_npm_registry_source(self):
        # Operator-configured mirror.npm.
        sys.modules["core.settings_service"]._npm_registry = "https://npm.ir/mirror/"
        log = _RecordingLogger()
        self.d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=self._pkg_tar(),
            config=self._config(),
            logger=log,
        )
        gen = [e for e in log.entries if e["stage"] == "dockerfile_generation"]
        self.assertTrue(gen)
        last = gen[-1]
        self.assertEqual(last["details"].get("npm_registry"), "https://npm.ir/mirror/")
        self.assertEqual(last["details"].get("npm_registry_source"), "operator_setting")
        # The full list of detected files must be in the log so the user
        # can verify the platform actually looked at their archive.
        self.assertIn("package.json", last["details"].get("detected_files", []))
        self.assertEqual(last["details"].get("package_json_path"), "package.json")

    def test_dockerfile_generation_log_reports_user_npm_registry_override(self):
        # Operator default, user overrides via config.frontend.npm_registry.
        sys.modules["core.settings_service"]._npm_registry = "https://registry.npmjs.org"
        log = _RecordingLogger()
        self.d._inject_laravel_frontend_build(
            "FROM mirror.test/php:8.4-apache\nCOPY . /var/www/html/\nEXPOSE 80\n",
            tar_stream=self._pkg_tar(),
            config=self._config(frontend={"npm_registry": "https://tenant/mirror/"}),
            logger=log,
        )
        gen = [e for e in log.entries if e["stage"] == "dockerfile_generation"]
        self.assertTrue(gen)
        last = gen[-1]
        self.assertEqual(last["details"].get("npm_registry"), "https://tenant/mirror/")
        self.assertEqual(last["details"].get("npm_registry_source"), "user_override")


# ---------------------------------------------------------------------------
# Issue 4 — settings_service exposes mirror_composer / mirror_go
# ---------------------------------------------------------------------------


class SettingsServiceMirrorTests(unittest.TestCase):
    def test_mirror_functions_are_defined(self):
        # Read the source file so the test doesn't need Django's app
        # registry (settings_service imports django.core.cache which
        # requires configured settings).
        from pathlib import Path
        src_path = Path(__file__).parents[2].joinpath(
            "core", "settings_service.py"
        )
        self.assertTrue(src_path.is_file(),
                        msg="core/settings_service.py must exist")
        source = src_path.read_text()
        # Each mirror_* function must be defined with `def name() -> str:`.
        for fn in ("mirror_docker", "mirror_python", "mirror_npm",
                   "mirror_composer", "mirror_apt", "mirror_go"):
            self.assertIn(f"def {fn}(", source,
                          msg=f"core/settings_service.py must define {fn}() "
                              "so the Laravel frontend build can read the "
                              "operator-configured npm/composer/etc. mirror.")


if __name__ == "__main__":
    unittest.main()
