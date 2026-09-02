"""Unit tests for the risk-based restricted shell policy.

These tests exercise pure policy functions without Docker or a live database.
"""
from __future__ import annotations

import os
import sys
import types
from unittest import mock

import pytest

# Minimal stubs so services.shell can be imported outside a full Django project.
if "django" not in sys.modules:
    django = types.ModuleType("django")
    sys.modules["django"] = django

    core = types.ModuleType("django.core")
    sys.modules["django.core"] = core
    exceptions = types.ModuleType("django.core.exceptions")

    class ValidationError(Exception):
        def __init__(self, message):
            if isinstance(message, list):
                self.messages = message
                super().__init__(message[0] if message else "")
            else:
                self.messages = [str(message)]
                super().__init__(str(message))

    exceptions.ValidationError = ValidationError
    sys.modules["django.core.exceptions"] = exceptions

    db = types.ModuleType("django.db")
    sys.modules["django.db"] = db
    db.transaction = types.SimpleNamespace(atomic=lambda: mock.MagicMock())
    models_mod = types.ModuleType("django.db.models")
    models_mod.Q = object
    sys.modules["django.db.models"] = models_mod

    utils = types.ModuleType("django.utils")
    sys.modules["django.utils"] = utils
    timezone = types.ModuleType("django.utils.timezone")
    timezone.now = lambda: None
    sys.modules["django.utils.timezone"] = timezone

    for name in (
        "deployments",
        "deployments.core",
        "deployments.core.manager",
        "deployments.core.manager.client_manager",
        "docker",
        "docker.errors",
        "deploy",
        "deploy.models",
        "services.models",
    ):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)

    sys.modules["deployments.core.manager.client_manager"].Client = object
    sys.modules["docker.errors"].APIError = Exception
    sys.modules["docker.errors"].NotFound = Exception


# Ensure the local package path is importable.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.shell import (  # noqa: E402
    ARTISAN_NAME_RE,
    FORBIDDEN_BASENAMES,
    Risk,
    ShellPolicyError,
    _is_destructive_command,
    _validate_platform_command,
    classify_command_risk,
    parse_safe_command,
)


ROOT_PATH = "/var/www/html"


def allow(argv, platform="laravel", allow_advanced=False):
    _validate_platform_command(argv, platform, ROOT_PATH, allow_advanced=allow_advanced)


def reject(argv, platform="laravel", allow_advanced=False, code=None):
    with pytest.raises((ShellPolicyError, Exception)) as excinfo:
        _validate_platform_command(argv, platform, ROOT_PATH, allow_advanced=allow_advanced)
    if code is not None and isinstance(excinfo.value, ShellPolicyError):
        assert excinfo.value.shell_code == code
    return excinfo.value


# ---------------------------------------------------------------------------
# Dangerous binaries stay blocked
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "sh", "bash", "ash", "zsh", "busybox", "sudo", "su",
    "docker", "podman", "kubectl", "kill", "pkill", "chmod", "chown",
    "apt", "apk", "wget", "nc", "netcat",
])
def test_forbidden_binaries_blocked(cmd):
    reject([cmd])
    reject([cmd, "--help"])


# ---------------------------------------------------------------------------
# PHP / Artisan
# ---------------------------------------------------------------------------

def test_php_artisan_migrate_allowed():
    allow(["php", "artisan", "migrate"])
    assert not _is_destructive_command(["php", "artisan", "migrate"])
    assert classify_command_risk(["php", "artisan", "migrate"]) == Risk.NORMAL_MUTATION


def test_php_artisan_migrate_status_allowed():
    allow(["php", "artisan", "migrate:status"])
    assert classify_command_risk(["php", "artisan", "migrate:status"]) == Risk.READ_ONLY


def test_php_artisan_route_list_allowed():
    allow(["php", "artisan", "route:list"])


def test_php_artisan_custom_command_allowed():
    allow(["php", "artisan", "app:sync-users"])
    assert not _is_destructive_command(["php", "artisan", "app:sync-users"])
    assert classify_command_risk(["php", "artisan", "app:sync-users"]) == Risk.NORMAL_MUTATION


def test_php_artisan_destructive_requires_confirm():
    allow(["php", "artisan", "migrate:fresh"])
    assert _is_destructive_command(["php", "artisan", "migrate:fresh"])
    assert classify_command_risk(["php", "artisan", "migrate:fresh"]) == Risk.DESTRUCTIVE


def test_php_inline_eval_blocked():
    reject(["php", "-r", "echo 1;"])
    reject(["php", "script.php"])


def test_php_tinker_requires_advanced():
    reject(["php", "artisan", "tinker"], allow_advanced=False, code="AUTHORIZATION_FAILED")
    allow(["php", "artisan", "tinker"], allow_advanced=True)


def test_php_on_generic_platform_allowed():
    """Platform mis-detection must not block php."""
    allow(["php", "artisan", "migrate"], platform="generic")
    allow(["php", "-v"], platform="node")


# ---------------------------------------------------------------------------
# Django / Python
# ---------------------------------------------------------------------------

def test_django_migrate_allowed():
    allow(["python", "manage.py", "migrate"], platform="django")
    assert not _is_destructive_command(["python", "manage.py", "migrate"])


def test_django_custom_command_allowed():
    allow(["python", "manage.py", "import_data"], platform="django")


def test_python_eval_blocked():
    reject(["python", "-c", "print(1)"], platform="django")
    reject(["python3", "script.py"], platform="python")


def test_django_shell_requires_advanced():
    reject(["python", "manage.py", "shell"], platform="django", allow_advanced=False)
    allow(["python", "manage.py", "shell"], platform="django", allow_advanced=True)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def test_npm_run_scripts_allowed():
    allow(["npm", "run", "build"], platform="node")
    allow(["npm", "run", "test"], platform="node")
    allow(["npm", "run", "lint"], platform="node")
    allow(["npm", "run", "typecheck"], platform="node")
    allow(["npm", "run", "my-custom-script"], platform="node")
    assert not _is_destructive_command(["npm", "run", "build"])


def test_npm_install_is_destructive():
    allow(["npm", "install"], platform="node")
    assert _is_destructive_command(["npm", "install"])


def test_yarn_pnpm_scripts_allowed():
    allow(["yarn", "build"], platform="node")
    allow(["pnpm", "run", "test"], platform="node")


def test_npx_common_tools_allowed():
    allow(["npx", "vite", "build"], platform="node")
    allow(["npx", "eslint", "."], platform="node")
    allow(["npx", "@vitejs/plugin-react"], platform="node")


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

def test_git_read_only_allowed():
    for cmd in (
        ["git", "status"],
        ["git", "log", "--oneline", "-10"],
        ["git", "diff"],
        ["git", "show", "HEAD"],
        ["git", "branch", "-a"],
        ["git", "rev-parse", "HEAD"],
        ["git", "remote", "-v"],
    ):
        allow(cmd, platform="generic")
        assert not _is_destructive_command(cmd)


def test_git_reset_is_destructive():
    allow(["git", "reset", "--hard"], platform="generic")
    assert _is_destructive_command(["git", "reset", "--hard"])


def test_git_forbidden_subcommand():
    reject(["git", "daemon"], platform="generic")


# ---------------------------------------------------------------------------
# Filesystem / base tools
# ---------------------------------------------------------------------------

def test_base_commands_allowed():
    for cmd in (["pwd"], ["ls", "-la"], ["cat", "README.md"], ["mkdir", "tmp"]):
        allow(cmd)


def test_path_traversal_rejected():
    reject(["cat", "/etc/passwd"])
    reject(["ls", "../../etc"])


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_safe_command_rejects_redirects():
    with pytest.raises(Exception):
        parse_safe_command("ls > /tmp/out")
    with pytest.raises(Exception):
        parse_safe_command("echo $(whoami)")


def test_artisan_name_regex():
    assert ARTISAN_NAME_RE.fullmatch("migrate")
    assert ARTISAN_NAME_RE.fullmatch("migrate:status")
    assert ARTISAN_NAME_RE.fullmatch("app:sync-users")
    assert not ARTISAN_NAME_RE.fullmatch("../evil")
    assert not ARTISAN_NAME_RE.fullmatch("migrate;rm")


# ---------------------------------------------------------------------------
# Risk classification matrix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("argv,expected", [
    (["ls"], Risk.READ_ONLY),
    (["git", "status"], Risk.READ_ONLY),
    (["php", "artisan", "migrate"], Risk.NORMAL_MUTATION),
    (["php", "artisan", "migrate:fresh"], Risk.DESTRUCTIVE),
    (["rm", "file.txt"], Risk.DESTRUCTIVE),
    (["npm", "run", "build"], Risk.NORMAL_MUTATION),
    (["npm", "install"], Risk.DESTRUCTIVE),
    (["php", "artisan", "tinker"], Risk.INTERACTIVE),
])
def test_risk_matrix(argv, expected):
    assert classify_command_risk(argv) == expected
