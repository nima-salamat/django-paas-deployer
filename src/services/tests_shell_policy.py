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


def test_php_artisan_custom_command_requires_confirmation():
    allow(["php", "artisan", "app:sync-users"])
    assert _is_destructive_command(["php", "artisan", "app:sync-users"])
    assert classify_command_risk(["php", "artisan", "app:sync-users"]) == Risk.HIGH_IMPACT


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
    assert _is_destructive_command(["npm", "run", "build"])
    assert classify_command_risk(["npm", "run", "build"]) == Risk.HIGH_IMPACT


def test_npm_install_is_destructive():
    allow(["npm", "install"], platform="node")
    assert _is_destructive_command(["npm", "install"])


def test_yarn_pnpm_scripts_allowed():
    allow(["yarn", "build"], platform="node")
    allow(["pnpm", "run", "test"], platform="node")


def test_npx_common_tools_allowed_but_high_impact():
    for cmd in (
        ["npx", "vite", "build"],
        ["npx", "eslint", "."],
        ["npx", "@vitejs/plugin-react"],
    ):
        allow(cmd, platform="node")
        assert _is_destructive_command(cmd)
        assert classify_command_risk(cmd) == Risk.HIGH_IMPACT


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

def test_curl_is_not_available_in_restricted_shell():
    reject(["curl", "https://example.com"])

# ---------------------------------------------------------------------------
# WordPress / WP-CLI
# ---------------------------------------------------------------------------

def test_wp_cli_read_only_and_cache_operations():
    allow(["wp", "core", "version"], platform="wordpress")
    allow(["wp", "plugin", "list"], platform="wordpress")
    allow(["wp", "cache", "flush"], platform="wordpress")
    assert classify_command_risk(["wp", "core", "version"]) == Risk.READ_ONLY
    assert classify_command_risk(["wp", "plugin", "list"]) == Risk.READ_ONLY
    assert classify_command_risk(["wp", "cache", "flush"]) == Risk.NORMAL_MUTATION
    assert not _is_destructive_command(["wp", "cache", "flush"])

def test_wp_cli_publish_and_content_lifecycle_are_impact_aware():
    draft = ["wp", "post", "create", "--post_status=draft"]
    publish = ["wp", "post", "create", "--post_status=publish"]
    update = ["wp", "post", "update", "42", "--post_title=Updated"]
    publish_update = ["wp", "post", "update", "42", "--post_status=publish"]
    for cmd in (draft, publish, update, publish_update):
        allow(cmd, platform="wordpress")
    assert classify_command_risk(draft) == Risk.NORMAL_MUTATION
    assert classify_command_risk(update) == Risk.NORMAL_MUTATION
    assert classify_command_risk(publish) == Risk.HIGH_IMPACT
    assert classify_command_risk(publish_update) == Risk.HIGH_IMPACT
    assert _is_destructive_command(publish)
    assert _is_destructive_command(publish_update)

def test_wp_cli_privileged_operations_require_confirmation():
    commands = [
        ["wp", "plugin", "activate", "example"],
        ["wp", "theme", "activate", "example"],
        ["wp", "user", "create", "alice", "alice@example.com"],
        ["wp", "user", "set-role", "42", "administrator"],
        ["wp", "config", "set", "DISALLOW_FILE_MODS", "false"],
    ]
    for cmd in commands:
        allow(cmd, platform="wordpress")
        assert classify_command_risk(cmd) == Risk.PRIVILEGED
        assert _is_destructive_command(cmd)

def test_wp_cli_plugin_install_is_high_impact_and_not_implicitly_activated():
    cmd = ["wp", "plugin", "install", "example"]
    allow(cmd, platform="wordpress")
    assert classify_command_risk(cmd) == Risk.HIGH_IMPACT
    assert _is_destructive_command(cmd)

def test_wp_cli_rejects_remote_resources_and_external_paths():
    reject(["wp", "plugin", "install", "https://example.com/plugin.zip"], platform="wordpress")
    reject(["wp", "media", "import", "https://example.com/file.jpg"], platform="wordpress")
    reject(["wp", "plugin", "install", "/etc/plugin.zip"], platform="wordpress")
    reject(["wp", "media", "import", "../../etc/file"], platform="wordpress")
    allow(["wp", "plugin", "install", "/var/www/html/plugin.zip"], platform="wordpress")

def test_wp_cli_rejects_code_loading_and_remote_transports():
    reject(["wp", "plugin", "list", "--require=/var/www/html/a.php"], platform="wordpress")
    reject(["wp", "plugin", "list", "--exec=echo"], platform="wordpress")
    reject(["wp", "plugin", "list", "--ssh=root@example.com"], platform="wordpress")
    reject(["wp", "plugin", "list", "--http=https://example.com"], platform="wordpress")


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
    (["php", "artisan", "custom:sync"], Risk.HIGH_IMPACT),
    (["rm", "file.txt"], Risk.DESTRUCTIVE),
    (["npm", "run", "build"], Risk.HIGH_IMPACT),
    (["npm", "install"], Risk.DESTRUCTIVE),
    (["wp", "core", "version"], Risk.READ_ONLY),
    (["wp", "cache", "flush"], Risk.NORMAL_MUTATION),
    (["wp", "plugin", "install", "example"], Risk.HIGH_IMPACT),
    (["wp", "plugin", "activate", "example"], Risk.PRIVILEGED),
    (["php", "artisan", "tinker"], Risk.INTERACTIVE),
])
def test_risk_matrix(argv, expected):
    assert classify_command_risk(argv) == expected
