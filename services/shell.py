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
DEFAULT_WORKDIRS = {"laravel": "/var/www/html", "php": "/var/www/html", "node": "/app", "python": "/app", "django": "/app", "generic": "/app"}

PLATFORM_ALIASES = {
    "laravel": "laravel", "php": "php", "django": "django", "python": "python",
    "flask": "python", "fastapi": "python", "node": "node", "node-express": "node",
    "nextjs": "node", "nuxt": "node", "react": "node", "vue": "node", "angular": "node",
}

BASE_COMMANDS = {
    "pwd", "ls", "cat", "head", "tail", "mkdir", "touch", "rm", "rmdir", "cp", "mv", "find",
    "grep", "wc", "sort", "uniq", "cut", "tr", "sed", "tee", "stat", "date", "whoami", "id", "env", "printenv", "which", "df", "du",
    "uname", "hostname", "ping", "curl", "cd",
}
PLATFORM_COMMANDS = {
    "laravel": {"php", "composer"},
    "php": {"php", "composer"},
    "django": {"python", "python3", "pip", "pip3"},
    "python": {"python", "python3", "pip", "pip3"},
    "node": {"node", "npm", "npx", "yarn", "pnpm"},
}
FORBIDDEN_BASENAMES = {
    "sh", "bash", "ash", "zsh", "fish", "dash", "busybox", "su", "sudo", "doas",
    "ssh", "scp", "sftp", "docker", "podman", "kubectl", "nsenter", "mount", "umount",
    "chroot", "iptables", "nft", "systemctl", "service", "kill", "pkill", "killall",
    "passwd", "useradd", "adduser", "userdel", "deluser", "groupadd", "groupdel",
    "chmod", "chown", "setcap", "capsh", "crontab", "apk", "apt", "apt-get", "dpkg",
    "curl-config", "wget", "nc", "netcat", "telnet",
}
PATH_ARG_COMMANDS = {"ls", "cat", "head", "tail", "mkdir", "touch", "rm", "rmdir", "cp", "mv", "find", "grep", "wc", "sort", "uniq", "cut", "tr", "sed", "tee", "stat", "du"}

# Commands that may change application state or availability. The API requires
# an explicit ``confirm=true`` for these operations. This is separate from the
# command allow-list so the shell can stay interactive without silently allowing
# destructive actions.
DESTRUCTIVE_COMMANDS = {
    ("php", "artisan", "migrate:fresh"),
    ("php", "artisan", "migrate:refresh"),
    ("php", "artisan", "down"),
    ("php", "artisan", "up"),
    ("php", "artisan", "db:seed"),
    ("composer", "update"),
    ("npm", "install"),
    ("npm", "ci"),
    ("yarn", "install"),
    ("pnpm", "install"),
}

ARTISAN_COMMAND_CATALOG = {
    "about": {"label": "Application information", "mutating": False},
    "list": {"label": "List Artisan commands", "mutating": False},
    "help": {"label": "Help for an Artisan command", "mutating": False},
    "tinker": {"label": "Laravel Tinker (advanced interactive)", "mutating": True, "interactive": True, "advanced": True},
    "admin:create": {"label": "Create application administrator", "mutating": True, "interactive": True, "advanced": False, "requires_confirmation": False},
    "route:list": {"label": "List application routes", "mutating": False},
    "route:clear": {"label": "Clear route cache", "mutating": True},
    "config:show": {"label": "Show configuration", "mutating": False},
    "config:clear": {"label": "Clear configuration cache", "mutating": True},
    "cache:clear": {"label": "Clear application cache", "mutating": True},
    "view:clear": {"label": "Clear compiled views", "mutating": True},
    "event:list": {"label": "List registered events", "mutating": False},
    "schedule:list": {"label": "List scheduled tasks", "mutating": False},
    "queue:monitor": {"label": "Show queue monitor status", "mutating": False},
    "storage:link": {"label": "Create the public storage symlink", "mutating": True},
    "migrate": {"label": "Run pending database migrations", "mutating": True},
    "migrate:status": {"label": "Show migration status", "mutating": False},
    "migrate:rollback": {"label": "Rollback the latest migrations", "mutating": True},
    "migrate:fresh": {"label": "Drop all tables and re-run migrations", "mutating": True, "destructive": True},
    "migrate:refresh": {"label": "Rollback and re-run all migrations", "mutating": True, "destructive": True},
    "db:seed": {"label": "Seed the database", "mutating": True, "destructive": True},
    "db:show": {"label": "Show database information", "mutating": False},
    "optimize": {"label": "Cache framework files", "mutating": True},
    "optimize:clear": {"label": "Clear framework caches", "mutating": True},
    "down": {"label": "Put the application into maintenance mode", "mutating": True, "destructive": True},
    "up": {"label": "Leave maintenance mode", "mutating": True},
}

GENERIC_COMMAND_CATALOG = {
    "pwd", "ls", "cat", "head", "tail", "mkdir", "touch", "rm", "cp", "mv", "find",
    "grep", "wc", "sort", "uniq", "cut", "tr", "sed", "tee", "stat", "date", "whoami", "id", "env", "printenv", "which",
    "df", "du", "uname", "hostname", "ping", "curl", "cd", "rmdir",
}


def _platform_for_service(service: Service) -> str:
    deploy = getattr(service, "selected_deploy", None)
    config = getattr(deploy, "config", None) or {}
    raw = str(config.get("framework") or config.get("platform") or "generic").strip().lower()
    return PLATFORM_ALIASES.get(raw, raw if raw in PLATFORM_COMMANDS else "generic")


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
FORBIDDEN_ARTISAN_PATTERNS = (re.compile(r"^(?:shell)$", re.I), re.compile(r"^(?:serve|queue:work|queue:listen|schedule:work)$", re.I))
FORBIDDEN_DJANGO_PATTERNS = (re.compile(r"^(?:shell|dbshell|runserver)$", re.I),)

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

def _validate_platform_command(argv: list[str], platform: str, root: str) -> None:
    if not argv: raise ValidationError("Command is required.")
    base=os.path.basename(argv[0]).lower()
    if base in FORBIDDEN_BASENAMES or base.startswith('docker'):
        raise ValidationError(f"Command '{base}' is not allowed.")
    allowed=BASE_COMMANDS | PLATFORM_COMMANDS.get(platform,set())
    if base not in allowed: raise ValidationError(f"Command '{base}' is not allowed for platform '{platform}'.")
    for token in argv[1:]:
        # Relative `..` is allowed when it resolves inside the workspace (for
        # example `cd ..` from /var/www/html/database). The old raw-token check
        # rejected the perfectly valid `..` before cwd-aware resolution.
        if base == 'cd':
            continue
        if '../' in token or token.startswith('..') or token.endswith('/..'):
            try:
                safe = _safe_workdir(token if token.startswith('/') else posixpath.join(root, token), root)
            except ValidationError:
                raise ValidationError('Path traversal outside the service workspace is not allowed.')
            if not _path_is_within(safe, root):
                raise ValidationError('Path traversal outside the service workspace is not allowed.')
        if token.startswith('/') and not _path_is_within(token,root) and not re.match(r'^https?://',token,re.I):
            raise ValidationError('Absolute paths outside the service workspace are not allowed.')
    if base=='find':
        if {a.lower() for a in argv[1:]} & {'-exec','-execdir','-ok','-okdir','-delete'}:
            raise ValidationError('find actions that execute or delete files are not allowed.')
        paths=[a for a in argv[1:] if not a.startswith('-') and not a.startswith('!')]
        if paths: _safe_workdir(paths[0],root)
    if base in {'rm','rmdir','cp','mv','mkdir','touch'}:
        _validate_mutating_paths(argv,root,base)
        if base=='rm' and '--no-preserve-root' in argv: raise ValidationError('--no-preserve-root is not allowed.')
    if base=='grep' and any(a in {'--exclude-from','--include-from'} for a in argv[1:]):
        raise ValidationError('grep option files are not allowed in the restricted shell.')
    if base == 'sed' and any(a in {'-i','--in-place'} or a.startswith('-i') for a in argv[1:]):
        raise ValidationError('sed in-place editing is not allowed; use the built-in file editor or tee.')
    if base == 'tee':
        paths=[a for a in argv[1:] if not a.startswith('-')]
        if not paths: raise ValidationError('tee requires a destination file.')
        if len(paths)>4: raise ValidationError('Too many tee destinations.')
    if base=='curl':
        urls=[a for a in argv[1:] if not a.startswith('-')]
        if not urls: raise ValidationError('curl requires a URL.')
        _validate_network_target(urls[-1])
    if base=='ping':
        targets=[a for a in argv[1:] if not a.startswith('-')]
        if not targets: raise ValidationError('ping requires a host.')
        _validate_network_target(targets[-1])
    if base=='php':
        if len(argv)<2: raise ValidationError('php requires a subcommand/script.')
        if argv[1]=='artisan':
            if len(argv)<3: raise ValidationError('php artisan requires a command.')
            cmd=argv[2]
            if not ARTISAN_NAME_RE.fullmatch(cmd): raise ValidationError('Invalid Artisan command name.')
            if any(rx.fullmatch(cmd) for rx in FORBIDDEN_ARTISAN_PATTERNS):
                raise ValidationError(f"Artisan command '{cmd}' is blocked because it opens an unrestricted shell/server/worker.")
            if cmd in {"tinker", "psysh"} and not allow_advanced:
                raise ValidationError("Artisan interactive developer tools require advanced shell permission.")
        elif argv[1] not in {'-v','--version','--ini','-m','--modules','-i','--info'}:
            raise ValidationError('Direct PHP script or inline execution is not allowed in the restricted shell.')
    if base=='composer' and (len(argv)<2 or argv[1] not in {'install','update','dump-autoload','show','validate','outdated','audit','why','depends','licenses'}):
        raise ValidationError('This Composer command is not allowed.')
    if base in {'python','python3'}:
        if len(argv)>=2 and argv[1]=='manage.py':
            if len(argv)<3 or not DJANGO_COMMAND_RE.fullmatch(argv[2]): raise ValidationError('Invalid Django manage.py command name.')
            if any(rx.fullmatch(argv[2]) for rx in FORBIDDEN_DJANGO_PATTERNS): raise ValidationError(f"Django command '{argv[2]}' is blocked because it opens an unrestricted shell/server.")
        elif len(argv)>=2: raise ValidationError('Arbitrary Python script/inline execution is not allowed.')
    if base in {'npm','yarn','pnpm'}:
        if len(argv)<2 or argv[1] not in {'install','ci','test','list','outdated','audit','view','why'}:
            raise ValidationError('This package-manager command is not allowed.')
    if base=='npx' and (len(argv)<2 or argv[1] not in {'vite','tsc','eslint','prettier'}): raise ValidationError('Only approved npx tools are allowed.')
    if base in {'pip','pip3'} and (len(argv)<2 or argv[1] not in {'install','list','show','freeze','check','index','wheel'}): raise ValidationError('This pip command is not allowed.')


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
    with transaction.atomic():
        active_qs = ShellSession.objects.select_for_update().filter(
            service=service, status=ShellSession.Status.ACTIVE
        )
        active = active_qs.filter(expires_at__gt=now).first()
        if active:
            raise ValidationError("This service already has an active shell session.")
        expired_ids = list(active_qs.filter(expires_at__lte=now).values_list("id", flat=True))
        if expired_ids:
            active_qs.filter(id__in=expired_ids).update(status=ShellSession.Status.EXPIRED)
        token = secrets.token_urlsafe(32)
        session = ShellSession.objects.create(
            service=service, user=user, token_hash=_token_hash(token),
            platform=platform, root_path=root, workdir=workdir,
            status=ShellSession.Status.ACTIVE,
            expires_at=_session_expiry(now),
        )
    return session, token


def terminate_active_session(service: Service, *, actor=None):
    """Revoke the single active shell session for a service.

    Shell commands are synchronous docker exec calls, so replacing a shell
    session only revokes the token/DB session; it does not kill the service
    container.
    """
    from services.models import ShellSession

    now = timezone.now()
    with transaction.atomic():
        qs = ShellSession.objects.select_for_update().filter(
            service=service, status=ShellSession.Status.ACTIVE
        )
        active = qs.filter(expires_at__gt=now).first()
        if not active:
            qs.filter(expires_at__lte=now).update(status=ShellSession.Status.EXPIRED)
            return None
        active.status = ShellSession.Status.CLOSED
        active.closed_at = now
        active.save(update_fields=["status", "closed_at"])
        return active


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


def _is_destructive_command(argv: list[str]) -> bool:
    if not argv: return False
    base=os.path.basename(argv[0]).lower()
    if tuple(argv[:3]) in DESTRUCTIVE_COMMANDS: return True
    if base=='php' and len(argv)>=3 and argv[1]=='artisan':
        meta=ARTISAN_COMMAND_CATALOG.get(argv[2])
        if meta:
            if meta.get('requires_confirmation') is False:
                return False
            return bool(meta.get('destructive'))
        return True
    if base in {'python','python3'} and len(argv)>=3 and argv[1]=='manage.py':
        return argv[2] in {'migrate','makemigrations','createsuperuser','changepassword','collectstatic','test'}
    if base in {'composer','pip','pip3'} and len(argv)>=2: return argv[1] in {'install','update','wheel'}
    if base == 'tee': return True
    return False

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

def validate_argv_for_container(argv, platform, root, container, *, allow_advanced: bool = False):
    allow_advanced = bool(allow_advanced)
    _validate_platform_command(argv,platform,root)
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
        if _is_destructive_command(argv) and not confirm: raise ValidationError('A command in this sequence changes application state. Confirmation is required.')
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


def command_catalog(platform: str) -> list[dict]:
    """Return platform-aware command metadata consumed by the terminal UI.

    ``interactive`` means the command is expected to keep a PTY open and may
    request stdin (for example Django's ``createsuperuser``).
    """
    items = [
        {"command": c, "label": c.replace("_", " "), "mutating": False, "dangerous": False, "interactive": False}
        for c in sorted(GENERIC_COMMAND_CATALOG)
    ]
    if platform in {"laravel", "php"}:
        items.extend(
            {"command": f"php artisan {name}", "label": meta["label"],
             "mutating": bool(meta.get("mutating")), "dangerous": bool(meta.get("destructive")), "interactive": bool(meta.get("interactive", False))}
            for name, meta in sorted(ARTISAN_COMMAND_CATALOG.items())
        )
        items.extend([
            {"command": "php -v", "label": "PHP version", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "php --ini", "label": "PHP ini location", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "php -m", "label": "PHP extensions", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "php -i", "label": "PHP information", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "composer show", "label": "Composer packages", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "composer validate", "label": "Validate composer.json", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "composer outdated", "label": "Outdated Composer packages", "mutating": False, "dangerous": False, "interactive": False},
        ])
    elif platform in {"django", "python"}:
        items += [
            {"command": "python --version", "label": "Python version", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "python manage.py check", "label": "Django system check", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "python manage.py showmigrations", "label": "List migrations", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "python manage.py migrate", "label": "Run migrations", "mutating": True, "dangerous": False, "interactive": False},
            {"command": "python manage.py makemigrations", "label": "Create migrations", "mutating": True, "dangerous": False, "interactive": False},
            {"command": "python manage.py createsuperuser", "label": "Create Django superuser", "mutating": True, "dangerous": False, "interactive": True, "input_mode": "line"},
            {"command": "python manage.py changepassword", "label": "Change Django user password", "mutating": True, "dangerous": False, "interactive": True, "input_mode": "line"},
            {"command": "python manage.py collectstatic", "label": "Collect static files", "mutating": True, "dangerous": False, "interactive": False},
            {"command": "pip list", "label": "Installed Python packages", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "pip freeze", "label": "Frozen Python requirements", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "pip check", "label": "Check Python dependencies", "mutating": False, "dangerous": False, "interactive": False},
        ]
    elif platform == "node":
        items += [
            {"command": "node --version", "label": "Node version", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "npm --version", "label": "npm version", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "npm list", "label": "Installed npm packages", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "npm outdated", "label": "Outdated npm packages", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "npm audit", "label": "Audit npm dependencies", "mutating": False, "dangerous": False, "interactive": False},
            {"command": "npm test", "label": "Run tests", "mutating": False, "dangerous": False, "interactive": False},
        ]
    # De-duplicate while preserving deterministic order.
    unique, seen = [], set()
    for item in items:
        if item["command"] in seen:
            continue
        seen.add(item["command"])
        unique.append(item)
    return unique

def execute_command(session, command: str, *, confirm: bool = False) -> dict:
    parts=parse_safe_command(command)
    if len(parts)>1: return execute_compound_command(session,command,confirm=confirm)
    argv=parts[0][0]; container=_resolve_container(session.service); validate_argv_for_container(argv,session.platform,session.root_path,container, allow_advanced=can_use_advanced_shell(session.service, session.user))
    if _is_destructive_command(argv) and not confirm: raise ValidationError('This command changes application state. Confirmation is required.')
    if argv[0]=='cd':
        if len(argv)>2: raise ValidationError('cd accepts one path.')
        target=argv[1] if len(argv)==2 else session.root_path
        candidate=target if target.startswith('/') else posixpath.join(session.workdir,target)
        safe=_safe_workdir(candidate,session.root_path)
        ok, resolved = _probe_directory(container, safe)
        if not ok:
            parent = posixpath.dirname(safe) or session.root_path
            try:
                probe = container.exec_run(["ls", "-ld", safe], workdir=parent, stdout=False, stderr=False, tty=False)
                exists = int(probe.exit_code if probe.exit_code is not None else 1) == 0
            except Exception:
                exists = False
            if exists:
                raise ValidationError(f'Directory exists but is not accessible to the container user: {safe}')
            raise ValidationError(f'Directory does not exist or is not accessible: {safe}')
        session.workdir=safe; now=timezone.now(); session.last_used_at=now; session.expires_at=_session_expiry(now); session.save(update_fields=['workdir','last_used_at','expires_at'])
        return {'exit_code':0,'stdout':safe+'\n','stderr':'','cwd':safe}
    if os.path.basename(argv[0]) in {'nano','vi','vim'}: raise ValidationError('Use the built-in file editor for text files.')
    if os.path.basename(argv[0]).lower() in {"mkdir","touch","rm","rmdir","cp","mv","tee"}:
        code,out,err=_run_mutating_argv(container,argv,session.workdir)
    else:
        code,out,err=_run_argv(container,argv,session.workdir)
    now=timezone.now(); session.last_used_at=now; session.expires_at=_session_expiry(now); session.save(update_fields=['last_used_at','expires_at'])
    return {'exit_code':code,'stdout':out[:MAX_OUTPUT_BYTES].decode('utf-8','replace'),'stderr':err[:MAX_OUTPUT_BYTES].decode('utf-8','replace'),'cwd':session.workdir}


def close_session(session) -> None:
    session.status = session.Status.CLOSED
    session.closed_at = timezone.now()
    session.save(update_fields=["status", "closed_at"])
