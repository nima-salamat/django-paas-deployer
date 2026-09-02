from __future__ import annotations

import json
import os
import posixpath
import re
import secrets
import shlex
import socket
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from deployments.core.manager.client_manager import Client
from docker.errors import APIError, NotFound as DockerNotFound

from deploy.models import Deploy
from services.models import Service


SESSION_TTL_MINUTES = 30
MAX_OUTPUT_BYTES = 64 * 1024
MAX_COMMAND_LENGTH = 4096
MAX_COMPOUND_SEGMENTS = 16
MAX_PIPE_INPUT_BYTES = 256 * 1024
MAX_FILE_SIZE = 256 * 1024
DEFAULT_WORKDIRS = {
    "laravel": "/var/www/html",
    "php": "/var/www/html",
    "node": "/app",
    "python": "/app",
    "django": "/app",
    "generic": "/app",
}

PLATFORM_ALIASES = {
    "laravel": "laravel",
    "php": "php",
    "lumen": "laravel",
    "django": "django",
    "python": "python",
    "flask": "python",
    "fastapi": "python",
    "node": "node",
    "node-express": "node",
    "nodejs": "node",
    "nextjs": "node",
    "nuxt": "node",
    "react": "node",
    "vue": "node",
    "angular": "node",
    "express": "node",
}

# ---------------------------------------------------------------------------
# Risk-based command policy
#
# Security boundary (always enforced):
#   authorization + container isolation + workspace confinement +
#   no user-controlled shell + explicit dangerous-binary bans + SSRF limits
#
# The allow surface is capability-oriented, not an exhaustive subcommand menu.
# Legitimate developer CLIs that stay inside the service container/workspace
# are accepted; dangerous execution mechanisms remain blocked.
# ---------------------------------------------------------------------------

class ShellPolicyError(ValidationError):
    """Policy/authorization failure with a stable machine-readable code."""

    def __init__(self, message: str, code: str = "POLICY_REJECTED"):
        super().__init__(message)
        self.shell_code = code


class Risk:
    READ_ONLY = "READ_ONLY"
    NORMAL_MUTATION = "NORMAL_MUTATION"
    DESTRUCTIVE = "DESTRUCTIVE"
    INTERACTIVE = "INTERACTIVE"
    PRIVILEGED = "PRIVILEGED"


# Safe filesystem / inspection utilities always available in every platform.
BASE_COMMANDS = {
    "pwd", "ls", "cat", "head", "tail", "mkdir", "touch", "rm", "rmdir", "cp", "mv",
    "find", "grep", "egrep", "fgrep", "wc", "sort", "uniq", "cut", "tr", "sed", "tee",
    "stat", "date", "whoami", "id", "env", "printenv", "which", "type", "df", "du",
    "uname", "hostname", "ping", "curl", "cd", "file", "basename", "dirname", "realpath",
    "md5sum", "sha256sum", "sha1sum", "cmp", "diff", "true", "false", "echo", "printf",
    "test", "[", "sleep", "expr",
}

# Runtime / package-manager binaries. Available regardless of platform label so
# a mis-detected framework does not block legitimate tools present in the image.
RUNTIME_COMMANDS = {
    "php", "composer",
    "python", "python3", "pip", "pip3",
    "node", "npm", "npx", "yarn", "pnpm", "bun",
    "git", "make",
}

# Platform label → preferred runtimes (advisory for catalogs / default workdir).
PLATFORM_COMMANDS = {
    "laravel": {"php", "composer", "node", "npm", "npx", "yarn", "pnpm", "git", "make"},
    "php": {"php", "composer", "git", "make"},
    "django": {"python", "python3", "pip", "pip3", "git", "make"},
    "python": {"python", "python3", "pip", "pip3", "git", "make"},
    "node": {"node", "npm", "npx", "yarn", "pnpm", "bun", "git", "make"},
    "generic": set(RUNTIME_COMMANDS),
}

# Explicitly blocked binaries — primary dangerous-command control.
FORBIDDEN_BASENAMES = {
    "sh", "bash", "ash", "zsh", "fish", "dash", "busybox", "csh", "tcsh", "ksh",
    "su", "sudo", "doas",
    "ssh", "scp", "sftp",
    "docker", "podman", "kubectl", "nerdctl", "crictl",
    "nsenter", "unshare", "mount", "umount", "chroot",
    "iptables", "nft", "ip6tables",
    "systemctl", "service", "init",
    "kill", "pkill", "killall", "killpg",
    "passwd", "useradd", "adduser", "userdel", "deluser", "groupadd", "groupdel", "usermod",
    "chmod", "chown", "chgrp", "setcap", "capsh", "setuid",
    "crontab", "at", "batch",
    "apk", "apt", "apt-get", "aptitude", "dpkg", "yum", "dnf", "rpm", "pacman", "zypper",
    "curl-config", "wget", "nc", "netcat", "ncat", "telnet", "socat",
    "perl", "ruby", "lua",  # arbitrary interpreters not part of the service runtime model
}

PATH_ARG_COMMANDS = {
    "ls", "cat", "head", "tail", "mkdir", "touch", "rm", "rmdir", "cp", "mv",
    "find", "grep", "egrep", "fgrep", "wc", "sort", "uniq", "cut", "tr", "sed",
    "tee", "stat", "du", "file", "realpath", "diff", "cmp",
}

# Artisan commands that are genuinely destructive (data loss / outage).
ARTISAN_DESTRUCTIVE = {
    "migrate:fresh", "migrate:refresh", "migrate:reset",
    "db:wipe", "db:seed",
    "down",
    "queue:flush", "queue:clear", "queue:prune-failed",
    "horizon:terminate", "horizon:clear",
}

# Artisan interactive / advanced tools.
ARTISAN_ADVANCED_INTERACTIVE = {"tinker", "psysh"}

# Artisan long-running workers that must stay bounded.
ARTISAN_ONE_SHOT_ONLY = {"queue:work", "queue:listen", "schedule:work", "serve", "horizon"}

# Django management commands that are destructive.
DJANGO_DESTRUCTIVE = {"flush", "reset_db"}

# Django interactive / advanced.
DJANGO_ADVANCED_INTERACTIVE = {"shell", "shell_plus", "dbshell"}

# Git subcommands / option patterns that are unsafe in this boundary.
GIT_FORBIDDEN_SUBCOMMANDS = {
    "daemon", "shell", "update-server-info",
}
GIT_DESTRUCTIVE_SUBCOMMANDS = {
    "reset", "clean", "checkout", "restore", "rebase", "push", "commit",
    "merge", "pull", "fetch", "add", "rm", "mv", "stash", "tag", "branch",
    "remote", "config", "init", "clone", "submodule", "filter-branch", "filter-repo",
}
# Read-only git subcommands never need confirmation.
GIT_READ_ONLY = {
    "status", "log", "diff", "show", "ls-files", "ls-remote", "rev-parse",
    "rev-list", "describe", "blame", "shortlog", "whatchanged", "name-rev",
    "cat-file", "ls-tree", "for-each-ref", "branch", "tag", "remote", "config",
    "help", "version",
}

# npm/yarn/pnpm lifecycle that is destructive (dependency tree rewrite).
PKG_DESTRUCTIVE_SUBS = {"install", "ci", "update", "upgrade", "add", "remove", "uninstall"}

# Catalog metadata for the UI (suggestions only — not the policy gate).
ARTISAN_COMMAND_CATALOG = {
    "about": {"label": "Application information", "risk": Risk.READ_ONLY},
    "list": {"label": "List Artisan commands", "risk": Risk.READ_ONLY},
    "help": {"label": "Help for an Artisan command", "risk": Risk.READ_ONLY},
    "tinker": {"label": "Laravel Tinker (advanced interactive)", "risk": Risk.INTERACTIVE, "interactive": True, "advanced": True},
    "queue:work": {"label": "Process one queue job (one-shot)", "risk": Risk.NORMAL_MUTATION},
    "schedule:run": {"label": "Run due scheduled tasks once", "risk": Risk.NORMAL_MUTATION},
    "route:list": {"label": "List application routes", "risk": Risk.READ_ONLY},
    "route:clear": {"label": "Clear route cache", "risk": Risk.NORMAL_MUTATION},
    "config:show": {"label": "Show configuration", "risk": Risk.READ_ONLY},
    "config:clear": {"label": "Clear configuration cache", "risk": Risk.NORMAL_MUTATION},
    "cache:clear": {"label": "Clear application cache", "risk": Risk.NORMAL_MUTATION},
    "view:clear": {"label": "Clear compiled views", "risk": Risk.NORMAL_MUTATION},
    "event:list": {"label": "List registered events", "risk": Risk.READ_ONLY},
    "schedule:list": {"label": "List scheduled tasks", "risk": Risk.READ_ONLY},
    "storage:link": {"label": "Create the public storage symlink", "risk": Risk.NORMAL_MUTATION},
    "migrate": {"label": "Run pending database migrations", "risk": Risk.NORMAL_MUTATION},
    "migrate:status": {"label": "Show migration status", "risk": Risk.READ_ONLY},
    "migrate:rollback": {"label": "Rollback the latest migrations", "risk": Risk.NORMAL_MUTATION},
    "migrate:fresh": {"label": "Drop all tables and re-run migrations", "risk": Risk.DESTRUCTIVE, "destructive": True},
    "migrate:refresh": {"label": "Rollback and re-run all migrations", "risk": Risk.DESTRUCTIVE, "destructive": True},
    "db:seed": {"label": "Seed the database", "risk": Risk.DESTRUCTIVE, "destructive": True},
    "db:show": {"label": "Show database information", "risk": Risk.READ_ONLY},
    "optimize": {"label": "Cache framework files", "risk": Risk.NORMAL_MUTATION},
    "optimize:clear": {"label": "Clear framework caches", "risk": Risk.NORMAL_MUTATION},
    "down": {"label": "Put the application into maintenance mode", "risk": Risk.DESTRUCTIVE, "destructive": True},
    "up": {"label": "Leave maintenance mode", "risk": Risk.NORMAL_MUTATION},
}

GENERIC_COMMAND_CATALOG = set(BASE_COMMANDS) | {"git", "make"}


def _platform_for_service(service: Service) -> str:
    """Resolve a stable platform label used for workdir defaults and UI catalogs.

    Platform is advisory for binary availability: runtime tools (php, python,
    node, git, …) are accepted on every platform so a mis-labelled deploy does
    not block legitimate developer commands. The label still drives the default
    work-root (Laravel → /var/www/html, others → /app).
    """
    deploy = getattr(service, "selected_deploy", None)
    config = getattr(deploy, "config", None) or {}
    candidates = [
        config.get("framework"),
        config.get("platform"),
        config.get("runtime"),
        config.get("stack"),
        getattr(deploy, "framework", None) if deploy is not None else None,
        getattr(service, "framework", None),
        getattr(service, "platform", None),
    ]
    for raw in candidates:
        value = str(raw or "").strip().lower()
        if not value:
            continue
        if value in PLATFORM_ALIASES:
            return PLATFORM_ALIASES[value]
        if value in PLATFORM_COMMANDS:
            return value
        # Partial matches (e.g. "laravel-10", "node18").
        for key, mapped in PLATFORM_ALIASES.items():
            if key in value or value in key:
                return mapped
    return "generic"


def _safe_workdir(path: str, root: str) -> str:
    path = str(path or root).strip() or root
    if not path.startswith("/"):
        path = posixpath.join(root, path)
    norm = posixpath.normpath(path)
    root_norm = posixpath.normpath(root)
    if norm != root_norm and not norm.startswith(root_norm.rstrip("/") + "/"):
        raise ValidationError("Work directory must stay inside the service work directory.")
    return norm


def _token_hash(token: str) -> str:
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _tokenize_shell(command: str) -> list[str]:
    if not isinstance(command, str) or not command.strip():
        raise ValidationError("Command is required.")
    if len(command) > MAX_COMMAND_LENGTH:
        raise ValidationError("Command is too long.")
    if "\x00" in command or "\r" in command:
        raise ValidationError("Invalid control characters in command.")
    lexer = shlex.shlex(command, posix=True, punctuation_chars="|;&<>")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError as exc:
        raise ValidationError(f"Invalid shell quoting: {exc}") from exc
    return tokens


def parse_safe_command(command: str) -> list[tuple[list[str], str | None]]:
    tokens = _tokenize_shell(command)
    if any(t in {">", ">>", "<", "<<", "<<<", "&", "&>"} or "$(" in t or "`" in t for t in tokens):
        raise ValidationError("Redirection, background jobs and command substitution are not allowed.")
    segments: list[tuple[list[str], str | None]] = []
    current: list[str] = []
    operator: str | None = None
    operators = {"|", "&&", "||", ";"}
    for token in tokens:
        if token in operators:
            if not current:
                raise ValidationError("Invalid command operator placement.")
            segments.append((current, operator))
            current=[]
            operator=token
        else:
            current.append(token)
    if not current:
        raise ValidationError("A command is required after the operator.")
    segments.append((current, operator))
    if len(segments) > MAX_COMPOUND_SEGMENTS:
        raise ValidationError(f"Too many command segments (maximum {MAX_COMPOUND_SEGMENTS}).")
    return [(a, None if i == 0 else op) for i,(a,op) in enumerate(segments)]


def _reject_shell_syntax(command: str) -> None:
    parse_safe_command(command)


def _validate_network_target(target: str) -> None:
    host = target
    if "://" in target:
        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValidationError("Only http/https URLs are allowed for curl.")
        host = parsed.hostname
    host = host.split("/")[0].split(":")[0].strip().lower()
    if host in {"localhost", "localhost.localdomain", "host.docker.internal"}:
        raise ValidationError("Local host targets are not allowed.")
    try:
        ip = socket.gethostbyname(host)
        octets = [int(x) for x in ip.split(".")]
        if (
            octets[0] in {10, 127} or
            (octets[0] == 169 and octets[1] == 254) or
            (octets[0] == 172 and 16 <= octets[1] <= 31) or
            (octets[0] == 192 and octets[1] == 168)
        ):
            raise ValidationError("Private or link-local network targets are not allowed.")
    except socket.gaierror:
        pass


def _non_option_args(argv: list[str], base: str) -> list[str]:
    """Return positional path-like arguments without mistaking option values for paths."""
    value_options = {
        "head": {"-n", "--lines", "-c", "--bytes"},
        "tail": {"-n", "--lines", "-c", "--bytes"},
        "cut": {"-b", "--bytes", "-c", "--characters", "-d", "--delimiter", "-f", "--fields", "-s"},
        "grep": {"-A", "-B", "-C", "--context", "--after-context", "--before-context", "-e", "--regexp", "-f", "--file"},
        "sed": {"-e", "--expression", "-f", "--file"},
    }
    result = []
    expects_value = False
    for token in argv[1:]:
        if expects_value:
            expects_value = False
            continue
        if token in value_options.get(base, set()):
            expects_value = True
            continue
        if token.startswith("--") and "=" in token:
            continue
        if token.startswith("-"):
            continue
        result.append(token)
    return result


def _validate_mutating_paths(argv: list[str], root: str, base: str) -> None:
    args = _non_option_args(argv, base)
    if base in {"rm", "rmdir"}:
        for arg in args:
            safe = _safe_workdir(arg, root)
            if safe == posixpath.normpath(root):
                raise ValidationError("The service work-root itself cannot be deleted.")
    elif base in {"cp", "mv"}:
        if len(args) < 2:
            raise ValidationError(f"{base} requires source and destination.")
        _safe_workdir(args[-1], root)
        for arg in args[:-1]:
            _safe_workdir(arg, root)
    elif base in {"mkdir", "touch"}:
        for arg in args:
            _safe_workdir(arg, root)



ARTISAN_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*(?::[a-z][a-z0-9_-]*)*$", re.I)
DJANGO_COMMAND_RE = re.compile(r"^[a-z][a-z0-9_-]*(?::[a-z0-9_-]+)*$", re.I)
FORBIDDEN_ARTISAN_PATTERNS = (
    re.compile(r"^(?:shell)$", re.I),
    re.compile(r"^(?:serve|queue:listen|schedule:work)$", re.I),
)
# queue:work is allowed only as a bounded one-shot (see _artisan_queue_work_allowed).
ONE_SHOT_ARTISAN_TIMEOUT_SECONDS = 120

FORBIDDEN_DJANGO_PATTERNS = (re.compile(r"^(?:dbshell|runserver)$", re.I),)
# manage.py shell is advanced-interactive (same gate as tinker), not hard-banned.


def _artisan_queue_work_allowed(argv: list[str]) -> bool:
    """Allow only bounded queue:work invocations (never infinite workers)."""
    flags = {a for a in argv[3:] if a.startswith("-")}
    joined = " ".join(argv[3:])
    if "--once" in flags or "--stop-when-empty" in flags:
        return True
    for a in argv[3:]:
        if a.startswith("--max-jobs="):
            try:
                return 1 <= int(a.split("=", 1)[1]) <= 50
            except ValueError:
                return False
        if a == "--max-jobs" and argv[3:].index(a) + 1 < len(argv[3:]):
            pass
    # --max-jobs N as two tokens
    for i, a in enumerate(argv[3:]):
        if a == "--max-jobs" and i + 1 < len(argv[3:]):
            try:
                return 1 <= int(argv[3:][i + 1]) <= 50
            except ValueError:
                return False
    return False


def can_use_advanced_shell(service: Service, user) -> bool:
    """Allow advanced interactive developer tools for owners or explicit shares."""
    if str(service.user_id) == str(user.id):
        return True
    try:
        from services.api.sharing import user_can_access_service
        allowed, _share = user_can_access_service(service, user, action="can_shell_advanced")
        return bool(allowed)
    except Exception:
        return False



def max_concurrent_shell_sessions() -> int:
    """Operator-configurable cap on active shell sessions per service."""
    try:
        from core.settings_service import get_int
        return max(1, min(get_int("shell.max_concurrent_sessions_per_service", 1), 20))
    except Exception:
        return 1


def record_shell_audit(
    *,
    service,
    user=None,
    session=None,
    action: str,
    command: str = "",
    path: str = "",
    cwd: str = "",
    exit_code=None,
    success: bool = True,
    detail: str = "",
    meta: dict | None = None,
    output_preview: str = "",
) -> None:
    """Persist a shell activity row. Never raises into the request path."""
    try:
        from services.models import ShellAuditEvent
        preview = (output_preview or "")[:4000]
        ShellAuditEvent.objects.create(
            service=service,
            user=user,
            session=session if getattr(session, "pk", None) else None,
            action=action,
            command=(command or "")[:8000],
            path=(path or "")[:1024],
            cwd=(cwd or "")[:512],
            exit_code=exit_code,
            success=bool(success),
            detail=(detail or "")[:4000],
            meta=meta or {},
            output_preview=preview,
        )
    except Exception:
        pass



def _path_is_within(path: str, root: str) -> bool:
    n=posixpath.normpath(path); r=posixpath.normpath(root)
    return n==r or n.startswith(r.rstrip('/')+'/')

def _container_mount_policy(container):
    try: container.reload()
    except Exception: pass
    root_ro=bool((container.attrs.get('HostConfig') or {}).get('ReadonlyRootfs', False))
    mounts=[]
    for m in container.attrs.get('Mounts') or []:
        d=posixpath.normpath(str(m.get('Destination') or ''))
        if d.startswith('/'): mounts.append((d,bool(m.get('RW',False))))
    mounts.sort(key=lambda x:len(x[0]), reverse=True)
    return root_ro,mounts

def _exec_test(container, args, fallback=None):
    """Run a tiny filesystem probe without invoking a user-controlled shell.

    Minimal images sometimes do not ship an external `test` binary. In that
    case fall back to `sh` only with fixed backend-generated arguments.
    """
    result = container.exec_run(args, stdout=False, stderr=False, tty=False)
    code = int(result.exit_code if result.exit_code is not None else 1)
    if code in (126, 127) and fallback is not None:
        result = container.exec_run(fallback, stdout=False, stderr=False, tty=False)
        code = int(result.exit_code if result.exit_code is not None else 1)
    return code


def path_access(container, path: str, *, for_create: bool=False, policy=None) -> dict:
    root_ro, mounts = policy if policy is not None else _container_mount_policy(container)
    target = posixpath.normpath(path)
    selected = None
    for mount_path, rw in mounts:
        if target == mount_path or target.startswith(mount_path.rstrip('/') + '/'):
            selected = rw
            break

    # ``mode`` describes the Docker mount/rootfs mode. ``writable`` describes
    # whether the actual container user can perform the requested operation.
    # Keeping these separate avoids falsely labelling an RW mount as RO just
    # because Unix ownership/permissions prevent the current uid from writing.
    mount_rw = (not root_ro) if selected is None else bool(selected)
    probe = posixpath.dirname(target) if for_create else target
    probe = probe or '/'

    mode_ok = False
    try:
        # Do not pass ``--`` here: some minimal images provide a shell/test
        # implementation that treats it differently. Absolute paths are
        # already normalized and constrained by _safe_workdir upstream.
        if for_create:
            dir_ok = _exec_test(container, ['test', '-d', probe], ['/bin/sh', '-c', 'test -d "$1"', 'probe', probe]) == 0
            write_ok = _exec_test(container, ['test', '-w', probe], ['/bin/sh', '-c', 'test -w "$1"', 'probe', probe]) == 0
            traverse_ok = _exec_test(container, ['test', '-x', probe], ['/bin/sh', '-c', 'test -x "$1"', 'probe', probe]) == 0
            mode_ok = dir_ok and write_ok and traverse_ok
        else:
            exists_ok = _exec_test(container, ['test', '-e', target], ['/bin/sh', '-c', 'test -e "$1"', 'probe', target]) == 0
            writable_ok = _exec_test(container, ['test', '-w', target], ['/bin/sh', '-c', 'test -w "$1"', 'probe', target]) == 0
            mode_ok = exists_ok and writable_ok
    except Exception:
        mode_ok = False

    writable = bool(mount_rw and mode_ok)
    return {
        'writable': writable,
        'mode': 'rw' if mount_rw else 'ro',
        'mount_writable': mount_rw,
        'effective_writable': mode_ok,
        'reason': 'Writable' if writable else (
            'Read-only filesystem/mount' if not mount_rw else
            'RW mount, but the container user has no write permission at this path'
        ),
    }

def batch_path_writable(container, paths: list[str], *, policy=None) -> dict[str, bool]:
    """Return effective write access for many paths with one container exec.

    Mount mode is handled separately. This probe is only the Unix permission
    layer, and uses a backend-owned fixed script with all paths supplied as
    argv values (never interpolated into a shell command).
    """
    unique = []
    seen = set()
    for path in paths:
        value = posixpath.normpath(str(path))
        if value not in seen:
            seen.add(value)
            unique.append(value)
    if not unique:
        return {}
    script = 'for p do if [ -d "$p" ]; then if [ -w "$p" ] && [ -x "$p" ]; then printf "1\n"; else printf "0\n"; fi; else if [ -w "$p" ]; then printf "1\n"; else printf "0\n"; fi; fi; done'
    try:
        result = container.exec_run(['/bin/sh', '-c', script, 'probe', *unique], stdout=True, stderr=False, tty=False)
        out = result.output if isinstance(result.output, (bytes, bytearray)) else b''
        if int(result.exit_code if result.exit_code is not None else 1) == 0:
            values = out.decode('utf-8', 'replace').splitlines()
            if len(values) == len(unique):
                return {path: values[i].strip() == '1' for i, path in enumerate(unique)}
    except Exception:
        pass
    # Fallback for images without a POSIX shell. This path is slower but only
    # used for unusual minimal containers or after a failed bulk probe.
    return {path: bool(path_access(container, path, policy=policy).get('effective_writable')) for path in unique}


def _assert_writable_path(container, path: str, *, for_create: bool = False, operation: str = "write"):
    """Validate mutability without confusing target-file mode with directory deletion rights.

    ``rm file`` needs write+execute permission on the parent directory, while
    editing an existing file needs write permission on the file itself. The
    Docker mount being RW is a separate fact and must never be presented as
    filesystem ``RO`` merely because the runtime UID lacks a mode bit.
    """
    access = path_access(container, path, for_create=(for_create or operation in {"create", "delete", "rename"}))
    if access.get("mount_writable"):
        if operation in {"delete", "rename"} and access.get("effective_writable"):
            return access
        if operation not in {"delete", "rename"} and access.get("writable"):
            return access
    if access.get("mount_writable"):
        raise ValidationError(f"Path is not writable by the service user: {path} (RW mount; the service user lacks the required filesystem permission).")
    raise ValidationError(f"Path is on a read-only Docker mount: {path}.")

def _policy_reject(message: str, code: str = "POLICY_REJECTED") -> None:
    raise ShellPolicyError(message, code=code)


def _validate_path_tokens(argv: list[str], base: str, root: str) -> None:
    """Reject path arguments that resolve outside the service work-root."""
    for token in argv[1:]:
        if base == "cd":
            continue
        if re.match(r"^https?://", token, re.I):
            continue
        if "../" in token or token == ".." or token.endswith("/.."):
            try:
                candidate = token if token.startswith("/") else posixpath.join(root, token)
                safe = _safe_workdir(candidate, root)
            except ValidationError as exc:
                _policy_reject(str(exc) or "Path traversal outside the service workspace is not allowed.")
            if not _path_is_within(safe, root):
                _policy_reject("Path traversal outside the service workspace is not allowed.")
        if token.startswith("/") and not _path_is_within(token, root):
            _policy_reject("Absolute paths outside the service workspace are not allowed.")


def _validate_php_argv(argv: list[str], *, allow_advanced: bool) -> None:
    if len(argv) < 2:
        _policy_reject("php requires a subcommand or info flag.")
    first = argv[1]
    if first in {"-v", "--version", "--ini", "-m", "--modules", "-i", "--info", "-l", "--syntax-check"}:
        return
    if first == "artisan":
        if len(argv) < 3:
            _policy_reject("php artisan requires a command name.")
        cmd = argv[2]
        if not ARTISAN_NAME_RE.fullmatch(cmd):
            _policy_reject(f"Invalid Artisan command name: {cmd}")
        if any(rx.fullmatch(cmd) for rx in FORBIDDEN_ARTISAN_PATTERNS):
            _policy_reject(
                f"Artisan command '{cmd}' is blocked because it opens an unrestricted shell, server, or long-running worker."
            )
        if cmd in ARTISAN_ONE_SHOT_ONLY and cmd == "queue:work" and not _artisan_queue_work_allowed(argv):
            _policy_reject(
                "queue:work is only allowed as a one-shot job. "
                "Use: php artisan queue:work --once   or   --max-jobs=1 --stop-when-empty"
            )
        if cmd in {"queue:listen", "schedule:work", "serve", "horizon"}:
            _policy_reject(
                f"Artisan command '{cmd}' is blocked because it starts a long-running server/worker. "
                "Use a bounded one-shot alternative when available."
            )
        if cmd in ARTISAN_ADVANCED_INTERACTIVE and not allow_advanced:
            _policy_reject(
                "Artisan interactive developer tools require advanced shell permission.",
                code="AUTHORIZATION_FAILED",
            )
        return
    # Arbitrary PHP scripts / inline eval stay blocked — they bypass framework
    # structure and are a common escape vector for unrestricted code execution.
    if first in {"-r", "--run", "-f", "-a", "--interactive"} or first.endswith(".php"):
        _policy_reject(
            "Direct PHP script or inline execution is not allowed. "
            "Use php artisan <command> for application operations."
        )
    _policy_reject(
        "Direct PHP script or inline execution is not allowed. "
        "Use php artisan <command> for application operations."
    )


def _validate_python_argv(argv: list[str], *, allow_advanced: bool) -> None:
    if len(argv) < 2:
        # bare `python` / `python3` — allow version banner via REPL-less invocation
        return
    first = argv[1]
    if first in {"-V", "--version", "-h", "--help"}:
        return
    if first == "manage.py":
        if len(argv) < 3:
            _policy_reject("python manage.py requires a command name.")
        cmd = argv[2]
        if not DJANGO_COMMAND_RE.fullmatch(cmd):
            _policy_reject(f"Invalid Django management command name: {cmd}")
        if any(rx.fullmatch(cmd) for rx in FORBIDDEN_DJANGO_PATTERNS):
            _policy_reject(
                f"Django command '{cmd}' is blocked because it opens an unrestricted shell or development server."
            )
        if cmd in DJANGO_ADVANCED_INTERACTIVE and not allow_advanced:
            _policy_reject(
                "Django interactive shell requires advanced shell permission.",
                code="AUTHORIZATION_FAILED",
            )
        return
    # Block eval / arbitrary script execution outside manage.py.
    if first in {"-c", "-m"} or first.endswith(".py"):
        _policy_reject(
            "Arbitrary Python script/inline execution is not allowed. "
            "Use python manage.py <command> for application operations."
        )
    _policy_reject(
        "Arbitrary Python script/inline execution is not allowed. "
        "Use python manage.py <command> for application operations."
    )


def _validate_composer_argv(argv: list[str]) -> None:
    if len(argv) < 2:
        _policy_reject("composer requires a subcommand.")
    # Composer is itself constrained; allow common developer verbs freely.
    # Dangerous OS-level behaviour is already prevented by container isolation.
    sub = argv[1].lstrip("-")
    if sub in {"version", "V"} or argv[1] in {"-V", "--version", "-h", "--help"}:
        return
    # Block composer exec / run-script with unrestricted shell helpers is hard;
    # allow standard package management and inspection verbs.
    blocked = {"exec", "run-script", "global", "self-update", "config"}
    if sub in blocked:
        _policy_reject(f"Composer subcommand '{sub}' is not allowed in the restricted shell.")


def _validate_node_pkg_argv(argv: list[str], base: str) -> None:
    """npm / yarn / pnpm / bun — allow project scripts without a static allowlist."""
    if len(argv) < 2:
        return  # version / help banners
    sub = argv[1]
    if sub in {"-v", "--version", "-h", "--help", "version", "help"}:
        return
    # Explicitly block lifecycle scripts that shell out to arbitrary system tools
    # outside the project model is impractical; we rely on container isolation.
    # Still reject known dangerous npm features.
    if sub in {"exec"} and base == "npm":
        # npm exec is similar to npx — allow with constrained package names below via npx path
        pass
    if sub in {"explore", "owner", "publish", "unpublish", "login", "adduser", "logout", "token", "access"}:
        _policy_reject(f"Package-manager subcommand '{sub}' is not allowed.")
    # `npm run <script>` / `yarn <script>` / `pnpm run <script>` — script names
    # are constrained to safe identifier characters; no shell metacharacters.
    if sub == "run":
        if len(argv) >= 3 and not re.fullmatch(r"[A-Za-z0-9:_./@+-]+", argv[2] or ""):
            _policy_reject("Invalid package script name.")
        return
    # yarn/pnpm often allow `yarn build` without `run`.
    if base in {"yarn", "pnpm", "bun"} and re.fullmatch(r"[A-Za-z0-9:_./@+-]+", sub or ""):
        return


def _validate_npx_argv(argv: list[str]) -> None:
    if len(argv) < 2:
        _policy_reject("npx requires a package/tool name.")
    tool = argv[1]
    if tool in {"-v", "--version", "-h", "--help"}:
        return
    # Allow common frontend/dev tools and scoped packages; reject shell-like names.
    if tool in FORBIDDEN_BASENAMES or tool.startswith("docker"):
        _policy_reject(f"npx tool '{tool}' is not allowed.")
    if not re.fullmatch(r"[@A-Za-z0-9._/-]+", tool):
        _policy_reject(f"Invalid npx tool name: {tool}")


def _validate_git_argv(argv: list[str], root: str) -> None:
    if len(argv) < 2:
        return
    sub = argv[1].lstrip("-")
    if argv[1] in {"-v", "--version", "-h", "--help"} or sub in {"help", "version"}:
        return
    if sub in GIT_FORBIDDEN_SUBCOMMANDS:
        _policy_reject(f"git {sub} is not allowed.")
    # Block options that can escape the workspace or execute helpers.
    joined = " ".join(argv[1:])
    dangerous_opts = (
        "--exec-path", "--upload-pack", "--receive-pack",
        "-c",  # config override can set core.sshCommand / pager etc. — still useful; we block specific patterns below
    )
    # Block explicit external command injection vectors.
    for token in argv[1:]:
        lower = token.lower()
        if lower.startswith("core.sshcommand") or lower.startswith("core.pager") or "gpg.program" in lower:
            _policy_reject("git configuration that overrides external programs is not allowed.")
        if lower in {"--upload-pack", "--receive-pack", "--exec-path"}:
            _policy_reject(f"git option '{token}' is not allowed.")
    # Restrict git -C / --git-dir / --work-tree to the workspace.
    for i, token in enumerate(argv[1:], start=1):
        if token in {"-C", "--git-dir", "--work-tree"} and i + 1 < len(argv):
            _safe_workdir(argv[i + 1] if argv[i + 1].startswith("/") else posixpath.join(root, argv[i + 1]), root)
        if token.startswith("--git-dir=") or token.startswith("--work-tree="):
            path = token.split("=", 1)[1]
            _safe_workdir(path if path.startswith("/") else posixpath.join(root, path), root)


def _validate_pip_argv(argv: list[str]) -> None:
    if len(argv) < 2:
        return
    sub = argv[1]
    if sub in {"-V", "--version", "-h", "--help"}:
        return
    blocked = {"uninstall", "download", "wheel", "hash", "debug", "config"}
    if sub in blocked:
        _policy_reject(f"pip subcommand '{sub}' is not allowed.")


def _validate_platform_command(argv: list[str], platform: str, root: str, *, allow_advanced: bool = False) -> None:
    """Risk-based command validation.

    Primary controls: forbidden binaries, no user shell, workspace paths,
    framework-specific escape hatches (php -r, python -c, long-running servers).
    Platform label does **not** gate binary availability.
    """
    if not argv:
        _policy_reject("Command is required.")
    base = os.path.basename(argv[0]).lower()

    if base in FORBIDDEN_BASENAMES or base.startswith("docker"):
        _policy_reject(f"Command '{base}' is not allowed.", code="POLICY_REJECTED")

    allowed = BASE_COMMANDS | RUNTIME_COMMANDS | PLATFORM_COMMANDS.get(platform, set()) | PLATFORM_COMMANDS.get("generic", set())
    if base not in allowed:
        _policy_reject(
            f"Command '{base}' is not allowed. "
            "The restricted shell permits workspace filesystem tools, framework CLIs, "
            "package managers, git, and make — not arbitrary system binaries.",
            code="POLICY_REJECTED",
        )

    _validate_path_tokens(argv, base, root)

    if base == "find":
        if {a.lower() for a in argv[1:]} & {"-exec", "-execdir", "-ok", "-okdir", "-delete"}:
            _policy_reject("find actions that execute or delete files are not allowed.")
        paths = [a for a in argv[1:] if not a.startswith("-") and not a.startswith("!")]
        if paths:
            _safe_workdir(paths[0], root)

    if base in {"rm", "rmdir", "cp", "mv", "mkdir", "touch"}:
        _validate_mutating_paths(argv, root, base)
        if base == "rm" and "--no-preserve-root" in argv:
            _policy_reject("--no-preserve-root is not allowed.")

    if base in {"grep", "egrep", "fgrep"} and any(a in {"--exclude-from", "--include-from"} for a in argv[1:]):
        _policy_reject("grep option files are not allowed in the restricted shell.")

    if base == "sed" and any(a in {"-i", "--in-place"} or a.startswith("-i") for a in argv[1:]):
        _policy_reject("sed in-place editing is not allowed; use the built-in file editor or tee.")

    if base == "tee":
        paths = [a for a in argv[1:] if not a.startswith("-")]
        if not paths:
            _policy_reject("tee requires a destination file.")
        if len(paths) > 4:
            _policy_reject("Too many tee destinations.")

    if base == "curl":
        urls = [a for a in argv[1:] if not a.startswith("-")]
        if not urls:
            _policy_reject("curl requires a URL.")
        _validate_network_target(urls[-1])

    if base == "ping":
        targets = [a for a in argv[1:] if not a.startswith("-")]
        if not targets:
            _policy_reject("ping requires a host.")
        _validate_network_target(targets[-1])

    if base == "php":
        _validate_php_argv(argv, allow_advanced=allow_advanced)
    elif base == "composer":
        _validate_composer_argv(argv)
    elif base in {"python", "python3"}:
        _validate_python_argv(argv, allow_advanced=allow_advanced)
    elif base in {"npm", "yarn", "pnpm", "bun"}:
        _validate_node_pkg_argv(argv, base)
    elif base == "npx":
        _validate_npx_argv(argv)
    elif base in {"pip", "pip3"}:
        _validate_pip_argv(argv)
    elif base == "git":
        _validate_git_argv(argv, root)
    elif base == "make":
        # make is allowed; recipes run inside the container under the same isolation.
        # Block overriding the shell used by make.
        for token in argv[1:]:
            if token.startswith("SHELL=") or token in {"-e", "--environment-overrides"} and False:
                pass
            if token.startswith("SHELL="):
                _policy_reject("Overriding make SHELL is not allowed.")
    elif base == "node":
        if len(argv) >= 2 and argv[1] in {"-e", "--eval", "-p", "--print"}:
            _policy_reject("Inline node eval is not allowed.")
        # `node script.js` is allowed when the script path stays in the workspace
        # (path tokens already validated above for absolute/traversal forms).


def _resolve_container(service: Service):
    name = service.get_docker_service_name()
    try:
        container = Client()().containers.get(name)
        container.reload()
        if str(container.status) != "running":
            raise ValidationError("Service container is not running.")
        return container
    except DockerNotFound as exc:
        raise ValidationError("Service container is not running or does not exist.") from exc


def shell_idle_timeout_minutes() -> int:
    """Read the operator-configured shell inactivity timeout."""
    try:
        from core.settings_service import shell_idle_timeout_minutes as _timeout
        return _timeout()
    except Exception:
        return 10


def _session_expiry(now):
    return now + timedelta(minutes=shell_idle_timeout_minutes())


def expire_idle_sessions(*, service=None, now=None) -> int:
    """Expire inactive shell sessions. Safe to call from API requests or monitor workers."""
    from services.models import ShellSession
    now = now or timezone.now()
    cutoff = now - timedelta(minutes=shell_idle_timeout_minutes())
    qs = ShellSession.objects.filter(status=ShellSession.Status.ACTIVE, last_used_at__lte=cutoff)
    if service is not None:
        qs = qs.filter(service=service)
    return qs.update(status=ShellSession.Status.EXPIRED, closed_at=now, expires_at=now)


def create_session(service: Service, user, workdir: str | None = None) -> tuple[object, str]:
    platform = _platform_for_service(service)
    root = DEFAULT_WORKDIRS.get(platform, "/app")
    workdir = _safe_workdir(workdir or root, root)
    _resolve_container(service)
    now = timezone.now()
    # Lazy import avoids model cycle during Django app loading.
    from services.models import ShellSession
    expire_idle_sessions(service=service, now=now)
    limit = max_concurrent_shell_sessions()
    with transaction.atomic():
        active_qs = ShellSession.objects.select_for_update().filter(
            service=service, status=ShellSession.Status.ACTIVE
        )
        # Expire stale rows first so they do not count against the limit.
        expired_ids = list(active_qs.filter(expires_at__lte=now).values_list("id", flat=True))
        if expired_ids:
            active_qs.filter(id__in=expired_ids).update(status=ShellSession.Status.EXPIRED)
        active_count = active_qs.filter(expires_at__gt=now).count()
        if active_count >= limit:
            raise ValidationError(
                f"This service already has {active_count} active shell session(s) "
                f"(limit {limit}). Close or replace an existing session first."
            )
        token = secrets.token_urlsafe(32)
        session = ShellSession.objects.create(
            service=service, user=user, token_hash=_token_hash(token),
            platform=platform, root_path=root, workdir=workdir,
            status=ShellSession.Status.ACTIVE,
            expires_at=_session_expiry(now),
        )
    try:
        record_shell_audit(
            service=service, user=user, session=session,
            action="session_open", cwd=workdir,
            detail=f"platform={platform} limit={limit}",
        )
    except Exception:
        pass
    return session, token


def terminate_active_session(service: Service, *, actor=None):
    """Revoke active shell session(s) for a service so a new one can be opened.

    Closes every active session for the service (respecting concurrent limits on
    the next create). Does not kill the service container.
    """
    from services.models import ShellSession

    now = timezone.now()
    with transaction.atomic():
        qs = ShellSession.objects.select_for_update().filter(
            service=service, status=ShellSession.Status.ACTIVE
        )
        qs.filter(expires_at__lte=now).update(status=ShellSession.Status.EXPIRED, closed_at=now)
        active_qs = qs.filter(expires_at__gt=now)
        first = active_qs.order_by("-last_used_at").first()
        closed = active_qs.update(status=ShellSession.Status.CLOSED, closed_at=now)
        if first:
            try:
                record_shell_audit(
                    service=service,
                    user=actor,
                    session=first,
                    action="session_replace",
                    detail=f"closed_active_sessions={closed}",
                )
            except Exception:
                pass
        return first if closed else None


def authenticate_session(service: Service, user, token: str):
    from services.models import ShellSession
    session = ShellSession.objects.filter(
        service=service, user=user, token_hash=_token_hash(str(token or "")), status=ShellSession.Status.ACTIVE
    ).first()
    if not session:
        raise ValidationError("Invalid or inactive shell session.")
    now = timezone.now()
    idle_cutoff = now - timedelta(minutes=shell_idle_timeout_minutes())
    if session.expires_at <= now or session.last_used_at <= idle_cutoff:
        ShellSession.objects.filter(pk=session.pk).update(
            status=ShellSession.Status.EXPIRED, closed_at=now, expires_at=now
        )
        raise ValidationError("Shell session expired due to inactivity.")
    return session


def classify_command_risk(argv: list[str]) -> str:
    """Return a Risk level for confirmation / UI purposes.

    READ_ONLY / NORMAL_MUTATION → no confirmation
    DESTRUCTIVE / PRIVILEGED → confirmation required
    INTERACTIVE → may need advanced permission (handled separately)
    """
    if not argv:
        return Risk.READ_ONLY
    base = os.path.basename(argv[0]).lower()

    if base in {"pwd", "ls", "cat", "head", "tail", "find", "grep", "egrep", "fgrep",
                "wc", "sort", "uniq", "cut", "tr", "stat", "date", "whoami", "id",
                "env", "printenv", "which", "type", "df", "du", "uname", "hostname",
                "file", "basename", "dirname", "realpath", "md5sum", "sha256sum",
                "sha1sum", "cmp", "diff", "true", "false", "echo", "printf", "sleep",
                "cd", "test"}:
        return Risk.READ_ONLY

    if base in {"rm", "rmdir"}:
        return Risk.DESTRUCTIVE
    if base in {"mkdir", "touch", "cp", "mv", "tee", "sed"}:
        return Risk.NORMAL_MUTATION if base != "tee" else Risk.DESTRUCTIVE

    if base == "php" and len(argv) >= 3 and argv[1] == "artisan":
        cmd = argv[2]
        if cmd in ARTISAN_ADVANCED_INTERACTIVE:
            return Risk.INTERACTIVE
        if cmd in ARTISAN_DESTRUCTIVE:
            return Risk.DESTRUCTIVE
        meta = ARTISAN_COMMAND_CATALOG.get(cmd)
        if meta:
            return meta.get("risk") or (Risk.DESTRUCTIVE if meta.get("destructive") else Risk.NORMAL_MUTATION)
        # Unknown / custom artisan commands are normal mutations, not destructive.
        return Risk.NORMAL_MUTATION

    if base == "php":
        return Risk.READ_ONLY

    if base in {"python", "python3"} and len(argv) >= 3 and argv[1] == "manage.py":
        cmd = argv[2]
        if cmd in DJANGO_ADVANCED_INTERACTIVE:
            return Risk.INTERACTIVE
        if cmd in DJANGO_DESTRUCTIVE:
            return Risk.DESTRUCTIVE
        if cmd in {"migrate", "makemigrations", "collectstatic", "createsuperuser",
                    "changepassword", "test", "loaddata", "dumpdata"}:
            return Risk.NORMAL_MUTATION
        return Risk.NORMAL_MUTATION

    if base in {"python", "python3"}:
        return Risk.READ_ONLY

    if base == "composer":
        sub = argv[1] if len(argv) >= 2 else ""
        if sub in {"install", "update", "require", "remove"}:
            return Risk.DESTRUCTIVE if sub in {"update", "remove"} else Risk.NORMAL_MUTATION
        return Risk.READ_ONLY

    if base in {"npm", "yarn", "pnpm", "bun"}:
        sub = argv[1] if len(argv) >= 2 else ""
        if sub in PKG_DESTRUCTIVE_SUBS:
            return Risk.DESTRUCTIVE
        if sub in {"run", "test", "start", "build"} or (
            base in {"yarn", "pnpm", "bun"} and sub and not sub.startswith("-")
        ):
            return Risk.NORMAL_MUTATION
        return Risk.READ_ONLY

    if base == "npx":
        return Risk.NORMAL_MUTATION

    if base in {"pip", "pip3"}:
        sub = argv[1] if len(argv) >= 2 else ""
        if sub in {"install", "uninstall"}:
            return Risk.DESTRUCTIVE if sub == "uninstall" else Risk.NORMAL_MUTATION
        return Risk.READ_ONLY

    if base == "git":
        sub = argv[1].lstrip("-") if len(argv) >= 2 else ""
        flags = {a for a in argv[2:] if a.startswith("-")}
        # Pure inspection.
        if sub in {"status", "log", "diff", "show", "ls-files", "rev-parse", "rev-list",
                   "describe", "blame", "shortlog", "whatchanged", "name-rev", "cat-file",
                   "ls-tree", "for-each-ref", "help", "version", "ls-remote"}:
            return Risk.READ_ONLY
        # Listing branches/tags/remotes is read-only; creating/deleting is destructive.
        if sub == "branch":
            if flags & {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy"}:
                return Risk.DESTRUCTIVE
            # `git branch newname` creates a branch.
            positionals = [a for a in argv[2:] if not a.startswith("-")]
            return Risk.DESTRUCTIVE if positionals else Risk.READ_ONLY
        if sub == "tag":
            positionals = [a for a in argv[2:] if not a.startswith("-")]
            if flags & {"-d", "--delete"} or positionals:
                return Risk.DESTRUCTIVE
            return Risk.READ_ONLY
        if sub == "remote":
            # `git remote -v` / `git remote` are read-only; add/remove/set-url mutate.
            positionals = [a for a in argv[2:] if not a.startswith("-")]
            if positionals and positionals[0] in {"add", "remove", "rm", "set-url", "rename", "prune"}:
                return Risk.DESTRUCTIVE
            return Risk.READ_ONLY
        if sub in {"reset", "clean"}:
            return Risk.DESTRUCTIVE
        if sub in GIT_DESTRUCTIVE_SUBCOMMANDS:
            return Risk.DESTRUCTIVE
        return Risk.READ_ONLY

    if base == "make":
        return Risk.NORMAL_MUTATION

    if base in {"curl", "ping"}:
        return Risk.READ_ONLY

    if base == "node":
        return Risk.NORMAL_MUTATION if len(argv) >= 2 else Risk.READ_ONLY

    return Risk.NORMAL_MUTATION


def _is_destructive_command(argv: list[str]) -> bool:
    """True when the command requires explicit confirm=true before execution."""
    risk = classify_command_risk(argv)
    return risk in {Risk.DESTRUCTIVE, Risk.PRIVILEGED}

def _assert_container_path_within(container, path: str, root: str) -> None:
    """Resolve a path inside the container and reject symlink/workspace escapes.

    Do not depend on ``realpath -m`` or ``readlink -f --`` because many production
    runtime images use BusyBox/minimal implementations with different flags.  The
    fallback uses only a backend-owned, fixed POSIX shell snippet and passes the
    user path as an argv value.
    """
    safe = _safe_workdir(path, root)
    root_norm = posixpath.normpath(root)
    target = None

    # First try the container's own realpath implementation for files, directories,
    # and symlinks. This prevents a symlinked file from escaping the workspace.
    try:
        probe = container.exec_run(
            ["/bin/sh", "-c", 'if command -v readlink >/dev/null 2>&1; then readlink -f "$1" 2>/dev/null; fi', "probe", safe],
            stdout=True, stderr=False, demux=False, tty=False,
        )
        out = probe.output if isinstance(probe.output, (bytes, bytearray)) else b""
        if int(probe.exit_code if probe.exit_code is not None else 1) == 0 and out:
            candidate = out.decode("utf-8", "replace").strip().splitlines()[-1:]
            target = candidate[0] if candidate else None
    except Exception:
        pass

    # Existing directory: canonicalise by entering it.
    if target is None:
        try:
            probe = container.exec_run(
                ["/bin/sh", "-c", 'cd "$1" 2>/dev/null && pwd -P', "probe", safe],
                stdout=True, stderr=False, demux=False, tty=False,
            )
            out = probe.output if isinstance(probe.output, (bytes, bytearray)) else b""
            if int(probe.exit_code if probe.exit_code is not None else 1) == 0 and out:
                candidate = out.decode("utf-8", "replace").strip().splitlines()[-1:]
                target = candidate[0] if candidate else None
        except Exception:
            pass

    # Existing file/symlink or missing target: canonicalise its parent and append
    # the basename. This also catches a symlink in any parent directory.
    if target is None:
        parent = posixpath.dirname(safe) or "/"
        name = posixpath.basename(safe)
        try:
            probe = container.exec_run(
                ["/bin/sh", "-c", 'cd "$1" 2>/dev/null && pwd -P', "probe", parent],
                stdout=True, stderr=False, demux=False, tty=False,
            )
            out = probe.output if isinstance(probe.output, (bytes, bytearray)) else b""
            if int(probe.exit_code if probe.exit_code is not None else 1) == 0 and out:
                canonical_parent = out.decode("utf-8", "replace").strip().splitlines()[-1:]
                if canonical_parent:
                    target = posixpath.join(canonical_parent[0], name)
        except Exception:
            pass

    if target is None or not _path_is_within(target, root_norm):
        raise ValidationError(f"Path resolves outside the service workspace: {path}")


def _command_path_arguments(argv):
    base=os.path.basename(argv[0]).lower()
    args = _non_option_args(argv, base)
    if base in {"grep"}:
        # grep's first positional argument is the pattern; remaining positionals are paths.
        return args[1:]
    if base in {"sed"}:
        return args[1:]
    if base in {"cut"}:
        return args[1:]
    if base in PATH_ARG_COMMANDS or base in {"sort", "uniq", "tr", "tee"}:
        return args
    return []


def prepare_interactive_exec_environment(container, *, platform: str = "", root_path: str = "") -> dict[str, str]:
    """Build an environment dict suitable for interactive REPLs (tinker/psysh/etc).

    PsySH writes config/history under ``$XDG_CONFIG_HOME/psysh`` (preferred)
    or ``$HOME/.config/psysh``. Our service containers usually run with
    ``ReadonlyRootfs=true``; only named volumes (Laravel ``storage``) and
    the ``/tmp`` tmpfs are writable.

    Strategy
    --------
    1. Prefer ``<root>/storage/psysh`` for Laravel/PHP (named volume).
    2. Fall back to ``/tmp/.config/psysh`` (tmpfs, always rw).
    3. Pre-create the chosen directory as root with mode 0777.
    4. Merge with the container's existing Env so PATH is preserved
       (Docker exec ``Env`` replaces the whole environment when set).
    """
    platform = (platform or "").strip().lower()
    root = (root_path or "").strip() or DEFAULT_WORKDIRS.get(platform, "/app")

    # (xdg_config_home, psysh_dir)
    options: list[tuple[str, str]] = []
    if platform in {"laravel", "php", "lumen", "symfony"}:
        storage = f"{root.rstrip('/')}/storage"
        options.append((storage, f"{storage}/psysh"))
    options.append(("/tmp/.config", "/tmp/.config/psysh"))
    options.append(("/tmp", "/tmp/psysh"))

    xdg_config = "/tmp/.config"
    psysh_dir = "/tmp/.config/psysh"
    home = "/tmp"

    for xdg, pdir in options:
        try:
            container.exec_run(
                [
                    "/bin/sh", "-c",
                    f"mkdir -p '{pdir}' && chmod 0777 '{pdir}' 2>/dev/null; "
                    f"chmod 0777 '{xdg}' 2>/dev/null; true",
                ],
                user="0",
                stdout=False,
                stderr=False,
                tty=False,
            )
            probe = container.exec_run(
                ["test", "-w", pdir],
                stdout=False,
                stderr=False,
                tty=False,
            )
            if int(probe.exit_code if probe.exit_code is not None else 1) == 0:
                xdg_config = xdg
                psysh_dir = pdir
                # HOME: keep app root for Laravel so other tools behave;
                # for /tmp fallbacks use /tmp.
                home = root if xdg.startswith(root.rstrip("/")) else "/tmp"
                break
        except Exception:
            continue

    # Preserve the container's existing environment (PATH, APP_*, etc.).
    env: dict[str, str] = {}
    try:
        container.reload()
        for item in (container.attrs.get("Config") or {}).get("Env") or []:
            if isinstance(item, str) and "=" in item:
                key, _, value = item.partition("=")
                if key:
                    env[key] = value
    except Exception:
        pass

    env["HOME"] = home
    env["XDG_CONFIG_HOME"] = xdg_config
    env["XDG_DATA_HOME"] = env.get("XDG_DATA_HOME") or "/tmp/.local/share"
    env["XDG_CACHE_HOME"] = env.get("XDG_CACHE_HOME") or "/tmp/.cache"
    env["PSYSH_CONFIG_DIR"] = psysh_dir
    # Give interactive REPLs a realistic terminal geometry so help tables
    # and pagers format correctly (Docker exec defaults can be very narrow).
    env["TERM"] = env.get("TERM") or "xterm-256color"
    env["COLUMNS"] = env.get("COLUMNS") or "120"
    env["LINES"] = env.get("LINES") or "40"
    return env


def validate_argv_for_container(argv, platform, root, container, *, allow_advanced: bool = False):
    allow_advanced = bool(allow_advanced)
    _validate_platform_command(argv, platform, root, allow_advanced=allow_advanced)
    base=os.path.basename(argv[0]).lower()
    for path_arg in _command_path_arguments(argv):
        # URL-like strings are data, not filesystem paths.
        if re.match(r'^https?://', path_arg, re.I):
            continue
        _assert_container_path_within(container, path_arg, root)
    # Mutating commands are permission-checked at execution time. The backend
    # can use its restricted file-manager fallback for RW mounts, so a Unix
    # permission mismatch must not masquerade as a read-only filesystem.


def _run_argv(container,argv,workdir,stdin_data=None):
    if stdin_data is None:
        result=container.exec_run(argv,workdir=workdir,stdout=True,stderr=True,demux=True,tty=False)
        out,err=result.output if isinstance(result.output,tuple) else (result.output or b'',b'')
        return int(result.exit_code or 0),out or b'',err or b''
    result=container.exec_run(argv,workdir=workdir,stdin=True,stdout=True,stderr=True,tty=False,socket=True)
    sock=result.output; target=getattr(sock,'_sock',sock)
    try:
        if stdin_data: target.sendall(stdin_data)
        try: target.shutdown(1)
        except Exception: pass
        chunks=[]
        while True:
            chunk=target.recv(32768)
            if not chunk: break
            chunks.append(chunk)
        return int(result.exit_code or 0),b''.join(chunks),b''
    finally:
        try: sock.close()
        except Exception: pass


def _run_argv_with_timeout(container, argv, workdir, *, timeout_seconds: int = 120):
    """Run argv with a hard wall-clock timeout; kill the exec if it overruns."""
    import concurrent.futures
    timeout_seconds = max(5, min(int(timeout_seconds or 120), 600))

    def _call():
        return _run_argv(container, argv, workdir)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_call)
        try:
            return fut.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            # Best-effort: Docker cannot easily kill a single exec from here;
            # return a controlled failure so the API never hangs forever.
            return (
                124,
                b"",
                f"Command timed out after {timeout_seconds}s and was aborted.\n".encode(),
            )



def _probe_directory(container, path: str) -> tuple[bool, str]:
    """Check a directory inside the running container using the real runtime user.

    Prefer the container's own POSIX shell because Docker's workdir validation can
    differ from the filesystem view. Fall back to ``ls -d`` for minimal images.
    Returns ``(accessible, resolved_path)``.
    """
    target = posixpath.normpath(path)
    try:
        result = container.exec_run(
            ["/bin/sh", "-c", 'cd "$1" 2>/dev/null && pwd -P', "probe", target],
            stdout=True, stderr=True, demux=True, tty=False,
        )
        out, _err = result.output if isinstance(result.output, tuple) else (result.output or b"", b"")
        if int(result.exit_code if result.exit_code is not None else 1) == 0:
            resolved = (out or b"").decode("utf-8", "replace").strip().splitlines()[-1:]
            return True, (resolved[0] if resolved else target)
    except Exception:
        pass
    try:
        result = container.exec_run(["ls", "-d", target], stdout=True, stderr=False, tty=False)
        out = result.output if isinstance(result.output, (bytes, bytearray)) else b""
        if int(result.exit_code if result.exit_code is not None else 1) == 0:
            return True, target
    except Exception:
        pass
    return False, target


def _run_mutating_argv(container, argv, workdir, stdin_data=None):
    """Run an already-validated mutation, retrying as root only when required.

    The argv has already passed the restricted parser and workspace-boundary
    validation. Root is used only as a backend-owned fallback for filesystem
    mutations; arbitrary commands can never reach this function.
    """
    base = os.path.basename(argv[0]).lower() if argv else ""
    can_manage = base in {"mkdir", "touch", "rm", "rmdir", "cp", "mv", "tee"}
    users = [None, "0"] if can_manage else [None]
    last = (1, b"", b"")
    for user in users:
        if stdin_data is None:
            result = container.exec_run(argv, workdir=workdir, stdout=True, stderr=True, demux=True, tty=False, **({"user": user} if user is not None else {}))
            out, err = result.output if isinstance(result.output, tuple) else (result.output or b"", b"")
            last = (int(result.exit_code if result.exit_code is not None else 1), out or b"", err or b"")
        else:
            result = container.exec_run(argv, workdir=workdir, stdin=True, stdout=True, stderr=True, tty=False, socket=True, **({"user": user} if user is not None else {}))
            sock = result.output; target = getattr(sock, "_sock", sock)
            try:
                if stdin_data: target.sendall(stdin_data)
                try: target.shutdown(1)
                except Exception: pass
                chunks=[]
                while True:
                    chunk=target.recv(32768)
                    if not chunk: break
                    chunks.append(chunk)
                last = (int(result.exit_code if result.exit_code is not None else 1), b"".join(chunks), b"")
            finally:
                try: sock.close()
                except Exception: pass
        if last[0] == 0:
            return last
    return last


def execute_compound_command(session,command,*,confirm=False):
    parts=parse_safe_command(command); container=_resolve_container(session.service); previous_code=0; previous_output=None; out=b''; err=b''
    for i,(argv,op) in enumerate(parts):
        if i>0:
            if op=='&&' and previous_code!=0: continue
            if op=='||' and previous_code==0: continue
        validate_argv_for_container(argv,session.platform,session.root_path,container, allow_advanced=can_use_advanced_shell(session.service, session.user))
        if _is_destructive_command(argv) and not confirm: raise ShellPolicyError('A command in this sequence is classified as destructive and requires confirmation.', code='CONFIRMATION_REQUIRED')
        if argv[0] == 'cd':
            if len(argv) > 2: raise ValidationError('cd accepts one path.')
            target=argv[1] if len(argv)==2 else session.root_path
            candidate=target if target.startswith('/') else posixpath.join(session.workdir,target)
            safe=_safe_workdir(candidate,session.root_path)
            _assert_container_path_within(container, safe, session.root_path)
            ok, resolved = _probe_directory(container, safe)
            if not ok:
                # A directory may exist but be inaccessible; distinguish that from
                # a genuine missing directory to avoid the old false-negative error.
                exists_probe = container.exec_run(["ls", "-ld", safe], stdout=False, stderr=False, tty=False)
                if int(exists_probe.exit_code if exists_probe.exit_code is not None else 1) == 0:
                    raise ValidationError(f'Directory exists but is not accessible to the container user: {safe}')
                raise ValidationError(f'Directory does not exist or is not accessible: {safe}')
            session.workdir=safe
            previous_code=0; out=(safe+'\n').encode(); err=b''; previous_output=out; final_stdout=out[:MAX_OUTPUT_BYTES]; final_stderr=b''
            continue
        stdin_data=previous_output if op=='|' else None
        if stdin_data is not None and len(stdin_data)>MAX_PIPE_INPUT_BYTES: raise ValidationError('Pipeline input exceeded the safety limit.')
        if os.path.basename(argv[0]).lower() in {"mkdir","touch","rm","rmdir","cp","mv","tee"}:
            previous_code,out,err=_run_mutating_argv(container,argv,session.workdir,stdin_data)
        else:
            previous_code,out,err=_run_argv(container,argv,session.workdir,stdin_data)
        previous_output=out
    now=timezone.now(); session.last_used_at=now; session.expires_at=_session_expiry(now); session.save(update_fields=['last_used_at','expires_at'])
    return {'stdout':out[:MAX_OUTPUT_BYTES].decode('utf-8','replace'),'stderr':err[:MAX_OUTPUT_BYTES].decode('utf-8','replace'),'exit_code':previous_code,'cwd':session.workdir}


def _catalog_item(command: str, label: str, *, risk: str = Risk.READ_ONLY, interactive: bool = False, advanced: bool = False) -> dict:
    return {
        "command": command,
        "label": label,
        "risk": risk,
        "mutating": risk in {Risk.NORMAL_MUTATION, Risk.DESTRUCTIVE, Risk.PRIVILEGED, Risk.INTERACTIVE},
        "dangerous": risk == Risk.DESTRUCTIVE,
        "interactive": interactive,
        "advanced": advanced,
    }


def command_catalog(platform: str) -> list[dict]:
    """Return platform-aware command *suggestions* for the terminal UI.

    This catalog is not the policy gate. Policy is enforced by
    ``_validate_platform_command`` / ``classify_command_risk``.
    """
    items = [
        _catalog_item(c, c.replace("_", " "), risk=Risk.READ_ONLY)
        for c in sorted(GENERIC_COMMAND_CATALOG)
    ]
    items.extend([
        _catalog_item("git status", "Git status", risk=Risk.READ_ONLY),
        _catalog_item("git log --oneline -20", "Git recent commits", risk=Risk.READ_ONLY),
        _catalog_item("git diff", "Git diff", risk=Risk.READ_ONLY),
        _catalog_item("git branch -a", "Git branches", risk=Risk.READ_ONLY),
        _catalog_item("git remote -v", "Git remotes", risk=Risk.READ_ONLY),
    ])

    if platform in {"laravel", "php", "generic"}:
        for name, meta in sorted(ARTISAN_COMMAND_CATALOG.items()):
            cmd = f"php artisan {name}"
            if name == "queue:work":
                cmd = "php artisan queue:work --once"
            items.append(_catalog_item(
                cmd, meta["label"],
                risk=meta.get("risk", Risk.NORMAL_MUTATION),
                interactive=bool(meta.get("interactive")),
                advanced=bool(meta.get("advanced")),
            ))
        items.extend([
            _catalog_item("php -v", "PHP version"),
            _catalog_item("php --ini", "PHP ini location"),
            _catalog_item("php -m", "PHP extensions"),
            _catalog_item("composer show", "Composer packages"),
            _catalog_item("composer validate", "Validate composer.json"),
            _catalog_item("composer outdated", "Outdated Composer packages"),
            _catalog_item("composer install", "Composer install", risk=Risk.NORMAL_MUTATION),
        ])

    if platform in {"django", "python", "generic"}:
        items.extend([
            _catalog_item("python --version", "Python version"),
            _catalog_item("python manage.py check", "Django system check"),
            _catalog_item("python manage.py showmigrations", "List migrations"),
            _catalog_item("python manage.py migrate", "Run migrations", risk=Risk.NORMAL_MUTATION),
            _catalog_item("python manage.py makemigrations", "Create migrations", risk=Risk.NORMAL_MUTATION),
            _catalog_item("python manage.py createsuperuser", "Create Django superuser", risk=Risk.NORMAL_MUTATION, interactive=True),
            _catalog_item("python manage.py shell", "Django shell (advanced interactive)", risk=Risk.INTERACTIVE, interactive=True, advanced=True),
            _catalog_item("python manage.py collectstatic", "Collect static files", risk=Risk.NORMAL_MUTATION),
            _catalog_item("pip list", "Installed Python packages"),
            _catalog_item("pip freeze", "Frozen Python requirements"),
        ])

    if platform in {"node", "laravel", "generic"}:
        items.extend([
            _catalog_item("node --version", "Node version"),
            _catalog_item("npm --version", "npm version"),
            _catalog_item("npm list", "Installed npm packages"),
            _catalog_item("npm outdated", "Outdated npm packages"),
            _catalog_item("npm audit", "Audit npm dependencies"),
            _catalog_item("npm test", "Run tests", risk=Risk.NORMAL_MUTATION),
            _catalog_item("npm run build", "Build (npm run build)", risk=Risk.NORMAL_MUTATION),
            _catalog_item("npm run lint", "Lint (npm run lint)", risk=Risk.NORMAL_MUTATION),
        ])

    unique, seen = [], set()
    for item in items:
        if item["command"] in seen:
            continue
        seen.add(item["command"])
        unique.append(item)
    return unique


def execute_command(session, command: str, *, confirm: bool = False, dry_run: bool = False) -> dict:
    parts = parse_safe_command(command)
    if len(parts) > 1:
        if dry_run:
            plan = []
            for argv, op in parts:
                plan.append({"argv": argv, "operator": op, "destructive": _is_destructive_command(argv), "risk": classify_command_risk(argv)})
            record_shell_audit(
                service=session.service, user=getattr(session, "user", None), session=session,
                action="command_dry_run", command=command, cwd=session.workdir,
                success=True, detail="compound", meta={"plan": plan},
            )
            return {
                "exit_code": 0, "stdout": "", "stderr": "", "cwd": session.workdir,
                "dry_run": True, "plan": plan,
            }
        result = execute_compound_command(session, command, confirm=confirm)
        record_shell_audit(
            service=session.service, user=getattr(session, "user", None), session=session,
            action="command", command=command, cwd=result.get("cwd") or session.workdir,
            exit_code=result.get("exit_code"), success=int(result.get("exit_code") or 0) == 0,
            output_preview=(result.get("stdout") or "")[:2000],
            detail=(result.get("stderr") or "")[:500],
        )
        return result

    argv = parts[0][0]
    container = _resolve_container(session.service)
    validate_argv_for_container(
        argv, session.platform, session.root_path, container,
        allow_advanced=can_use_advanced_shell(session.service, session.user),
    )
    if dry_run:
        plan = [{"argv": argv, "operator": None, "destructive": _is_destructive_command(argv), "risk": classify_command_risk(argv)}]
        record_shell_audit(
            service=session.service, user=getattr(session, "user", None), session=session,
            action="command_dry_run", command=command, cwd=session.workdir,
            success=True, meta={"plan": plan},
        )
        return {
            "exit_code": 0, "stdout": "", "stderr": "", "cwd": session.workdir,
            "dry_run": True, "plan": plan,
            "requires_confirmation": _is_destructive_command(argv), "risk": classify_command_risk(argv),
        }
    if _is_destructive_command(argv) and not confirm:
        raise ShellPolicyError("This command is classified as destructive and requires confirmation.", code="CONFIRMATION_REQUIRED")
    if argv[0] == "cd":
        if len(argv) > 2:
            raise ValidationError("cd accepts one path.")
        target = argv[1] if len(argv) == 2 else session.root_path
        candidate = target if target.startswith("/") else posixpath.join(session.workdir, target)
        safe = _safe_workdir(candidate, session.root_path)
        ok, resolved = _probe_directory(container, safe)
        if not ok:
            parent = posixpath.dirname(safe) or session.root_path
            try:
                probe = container.exec_run(["ls", "-ld", safe], workdir=parent, stdout=False, stderr=False, tty=False)
                exists = int(probe.exit_code if probe.exit_code is not None else 1) == 0
            except Exception:
                exists = False
            if exists:
                raise ValidationError(f"Directory exists but is not accessible to the container user: {safe}")
            raise ValidationError(f"Directory does not exist or is not accessible: {safe}")
        session.workdir = safe
        now = timezone.now()
        session.last_used_at = now
        session.expires_at = _session_expiry(now)
        session.save(update_fields=["workdir", "last_used_at", "expires_at"])
        result = {"exit_code": 0, "stdout": safe + "\n", "stderr": "", "cwd": safe}
        record_shell_audit(
            service=session.service, user=getattr(session, "user", None), session=session,
            action="command", command=command, cwd=safe, exit_code=0, success=True,
        )
        return result
    if os.path.basename(argv[0]) in {"nano", "vi", "vim"}:
        raise ValidationError("Use the built-in file editor for text files.")
    base_name = os.path.basename(argv[0]).lower()
    is_one_shot_job = (
        base_name == "php"
        and len(argv) >= 3
        and argv[1] == "artisan"
        and argv[2] in {"queue:work", "schedule:run"}
    )
    if base_name in {"mkdir", "touch", "rm", "rmdir", "cp", "mv", "tee"}:
        code, out, err = _run_mutating_argv(container, argv, session.workdir)
    elif is_one_shot_job:
        code, out, err = _run_argv_with_timeout(
            container, argv, session.workdir, timeout_seconds=ONE_SHOT_ARTISAN_TIMEOUT_SECONDS
        )
    else:
        code, out, err = _run_argv(container, argv, session.workdir)
    now = timezone.now()
    session.last_used_at = now
    session.expires_at = _session_expiry(now)
    session.save(update_fields=["last_used_at", "expires_at"])
    stdout = out[:MAX_OUTPUT_BYTES].decode("utf-8", "replace")
    stderr = err[:MAX_OUTPUT_BYTES].decode("utf-8", "replace")
    result = {"exit_code": code, "stdout": stdout, "stderr": stderr, "cwd": session.workdir}
    record_shell_audit(
        service=session.service, user=getattr(session, "user", None), session=session,
        action="command", command=command, cwd=session.workdir,
        exit_code=code, success=int(code or 0) == 0,
        output_preview=stdout[:2000], detail=stderr[:500],
        meta={"argv": argv},
    )
    return result


def close_session(session) -> None:
    session.status = session.Status.CLOSED
    session.closed_at = timezone.now()
    session.save(update_fields=["status", "closed_at"])
    try:
        record_shell_audit(
            service=session.service, user=getattr(session, "user", None), session=session,
            action="session_close", cwd=getattr(session, "workdir", "") or "",
        )
    except Exception:
        pass
