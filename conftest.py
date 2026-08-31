"""Pytest conftest — minimal Django + core stub setup for the tests.

The tests under ``deployments/tests/`` mostly need only the standard
library + the ``deployments`` package, but a few (docs public-auth,
settings_service mirror functions) require a Django app registry so
``rest_framework`` and ``django.core.cache`` can be imported.

This conftest also installs a comprehensive stub for
``core.global_settings.config`` so test modules that don't set up their
own stub (e.g. ``test_deployer_regressions.py``'s Deploy facade import)
can still import ``from core.global_settings.config import PlanTypeChoices``
without pulling in the full project Django models.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

# Make sure the backend root is importable. ``backend.zip`` was extracted
# to /home/z/my-project/work, so the work dir is the package root.
_WORK = Path(__file__).resolve().parents[1]
if str(_WORK) not in sys.path:
    sys.path.insert(0, str(_WORK))


# ---------------------------------------------------------------------------
# Pre-install a minimal ``core.global_settings.config`` stub so test modules
# that need PlanTypeChoices / MIRROR_DOCKER / Config can import them without
# triggering the full project Django models (which need Wagtail, channels,
# postgres, etc.). Test files may still overwrite this stub with their own
# (see test_patch_regressions.load_dockerfile_module).
# ---------------------------------------------------------------------------
def _install_core_stubs():
    if "core" not in sys.modules:
        core_pkg = types.ModuleType("core")
        core_pkg.__path__ = []
        sys.modules["core"] = core_pkg
    if "core.global_settings" not in sys.modules:
        gs_pkg = types.ModuleType("core.global_settings")
        gs_pkg.__path__ = []
        sys.modules["core.global_settings"] = gs_pkg
    if "core.global_settings.config" not in sys.modules:
        cfg = types.ModuleType("core.global_settings.config")
        cfg.MIRROR_DOCKER = "mirror.test"
        cfg.MIRROR_PYTHON = "https://pypi.org/simple"
        cfg.MIRROR_COMPOSER = ""
        cfg.MIRROR_NPM = "https://registry.npmjs.org"
        cfg.PLATFORM_CHOICES = []
        cfg.default_ports = {}
        cfg.DEFAULT_EXPOSE_PORT = 80
        cfg.DEFAULT_RUNTIME_VERSIONS = {}
        cfg.SERVICE_STATUS_CHOICES = []
        cfg.APPLICATIONS = []
        cfg.DBS = []
        cfg.COLORS = []
        cfg.COLOR_CHOICES = []
        cfg.DEFAULT_MAX_APPS = 2
        cfg.DEFAULT_RUNTIME_VERSIONS = {}
        cfg.DEFAULT_WORKER_COUNT = 1
        cfg.DEFAULT_SPA_BUILD_DIR = "dist"
        cfg.DEFAULT_EXPOSE_PORT = 80
        cfg.MAX_DEPLOY_TIME_MINUTE = 20
        class _PTC:
            DB = "DB"
            APP = "APP"
            READY = "READY"
        cfg.PlanTypeChoices = _PTC
        cfg.StorageTypeChoices = _PTC
        cfg.NameChoices = _PTC
        cfg.VOLUME_MODE_CHOICES = _PTC
        cfg.PaymentChoices = _PTC
        class _Config:
            php = ""
            laravel = ""
            python = ""
            django = ""
            flask = ""
            nextjs = ""
            nodejs = ""
            docker = ""
            go = ""
            static = ""
            vue = ""
            angular = ""
            react = ""
            dotnet = ""
            vuejs = ""
            statichtmlcss = ""
        cfg.Config = _Config
        sys.modules["core.global_settings.config"] = cfg


_install_core_stubs()


# ---------------------------------------------------------------------------
# Configure a minimal Django settings module on the fly. We do not want
# to load the project's full ``config/settings.py`` because that pulls in
# Wagtail, channels, postgres, etc. — none of which are installed in the
# test environment.
# ---------------------------------------------------------------------------
_MIN_SETTINGS = """
SECRET_KEY = "test-secret-key-for-patch-tests-only"
DEBUG = False
USE_TZ = True
TIME_ZONE = "UTC"
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "patch-tests",
    }
}
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_I18N = False
STATIC_URL = "/static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = "/tmp/patch-tests-media"
"""

_settings_mod = types.ModuleType("patch_test_settings")
exec(compile(_MIN_SETTINGS, "patch_test_settings.py", "exec"), _settings_mod.__dict__)
sys.modules["patch_test_settings"] = _settings_mod
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "patch_test_settings")

import django  # noqa: E402

from django.apps import apps as _apps  # noqa: E402

if not _apps.ready:
    django.setup()
