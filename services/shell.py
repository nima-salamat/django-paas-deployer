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
MAX_COMMAND_LENGTH = 512
MAX_FILE_SIZE = 256 * 1024
DEFAULT_WORKDIRS = {"laravel": "/var/www/html", "php": "/var/www/html", "node": "/app", "python": "/app", "django": "/app", "generic": "/app"}

PLATFORM_ALIASES = {
    "laravel": "laravel", "php": "php", "django": "django", "python": "python",
    "flask": "python", "fastapi": "python", "node": "node", "node-express": "node",
    "nextjs": "node", "nuxt": "node", "react": "node", "vue": "node", "angular": "node",
}

BASE_COMMANDS = {
    "pwd", "ls", "cat", "head", "tail", "mkdir", "touch", "rm", "cp", "mv", "find",
    "grep", "wc", "stat", "date", "whoami", "id", "env", "printenv", "which", "df", "du",
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
PATH_ARG_COMMANDS = {"ls", "cat", "head", "tail", "mkdir", "touch", "rm", "cp", "mv", "find", "grep", "wc", "stat", "du"}

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
    "grep", "wc", "stat", "date", "whoami", "id", "env", "printenv", "which",
    "df", "du", "uname", "hostname", "ping", "curl", "cd",
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


def _reject_shell_syntax(command: str) -> None:
    if not isinstance(command, str) or not command.strip():
        raise ValidationError("Command is required.")
    if len(command) > MAX_COMMAND_LENGTH:
        raise ValidationError("Command is too long.")
    forbidden = (";", "&&", "||", "|", ">", "<", "`", "$(", "${", "\\\n")
    if any(x in command for x in forbidden):
        raise ValidationError("Shell operators, redirection and command substitution are not allowed.")


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


def _validate_mutating_paths(argv: list[str], root: str, base: str) -> None:
    args = [a for a in argv[1:] if not a.startswith("-")]
    if base in {"rm", "rmdir"}:
        for arg in args:
            safe = _safe_workdir(arg, root) if arg.startswith("/") or not arg.startswith("-") else None
            if safe == posixpath.normpath(root):
                raise ValidationError("The service work-root itself cannot be deleted.")
    elif base in {"cp", "mv"}:
        if len(args) < 2:
            raise ValidationError(f"{base} requires source and destination.")
        # Both source and destination must remain inside the work root.
        _safe_workdir(args[-1], root)
        for arg in args[:-1]:
            _safe_workdir(arg, root)
    elif base in {"mkdir", "touch"}:
        for arg in args:
            _safe_workdir(arg, root)


def _validate_platform_command(argv: list[str], platform: str, root: str) -> None:
    if not argv:
        raise ValidationError("Command is required.")
    base = os.path.basename(argv[0])
    if base in FORBIDDEN_BASENAMES or base.startswith("docker"):
        raise ValidationError(f"Command '{base}' is not allowed.")
    allowed = BASE_COMMANDS | PLATFORM_COMMANDS.get(platform, set())
    if base not in allowed:
        raise ValidationError(f"Command '{base}' is not allowed for platform '{platform}'.")
    if base == "curl":
        urls = [a for a in argv[1:] if not a.startswith("-")]
        if not urls:
            raise ValidationError("curl requires a URL.")
        _validate_network_target(urls[-1])
    if base == "ping":
        targets = [a for a in argv[1:] if not a.startswith("-")]
        if not targets:
            raise ValidationError("ping requires a host.")
        _validate_network_target(targets[-1])
    if base in {"rm", "cp", "mv", "mkdir", "touch", "find", "grep", "cat", "head", "tail", "ls", "stat", "du", "wc"}:
        _validate_mutating_paths(argv, root, base)
        for arg in argv[1:]:
            if arg.startswith("-"):
                continue
            if base != "grep" and arg.startswith("/") and (arg.startswith("/proc") or arg.startswith("/sys") or arg.startswith("/dev") or arg.startswith("/etc")):
                raise ValidationError("Host/infrastructure paths are not accessible from the restricted shell.")
    if base == "php":
        if len(argv) < 2:
            raise ValidationError("php requires a subcommand/script.")
        if argv[1] == "artisan":
            if len(argv) < 3:
                raise ValidationError("php artisan requires a command.")
            allowed_artisan = {
                # Safe/read-only or routine operational Laravel commands
                "about", "list", "help", "route:list", "route:clear",
                "config:show", "config:clear", "cache:clear", "view:clear",
                "event:list", "schedule:list", "queue:monitor", "storage:link",
                # Database/schema maintenance
                "migrate", "migrate:status", "migrate:rollback",
                "migrate:fresh", "migrate:refresh", "db:seed", "db:show",
                # Common framework/cache maintenance
                "optimize", "optimize:clear", "down", "up",
            }
            command = argv[2]
            if command not in allowed_artisan:
                raise ValidationError(
                    "This Laravel Artisan command is not allowed by the restricted shell. "
                    "Project-specific Artisan commands must be explicitly enabled by the service/admin policy."
                )
            # Keep destructive migrate/down commands explicit and disallow arbitrary arguments that could
            # select or mutate an unexpected environment. Routine flags are limited below.
            if command in {"migrate:fresh", "migrate:refresh", "down", "up"}:
                allowed_flags = {"--force", "--seed", "--step", "--graceful", "--render", "--retry", "--refresh"}
                for token in argv[3:]:
                    if token.startswith("--") and token.split("=", 1)[0] not in allowed_flags:
                        raise ValidationError(f"Artisan flag '{token}' is not allowed.")
            elif command in {"migrate", "migrate:rollback", "db:seed"}:
                allowed_flags = {"--force", "--step", "--seed", "--class"}
                for token in argv[3:]:
                    if token.startswith("--") and token.split("=", 1)[0] not in allowed_flags:
                        raise ValidationError(f"Artisan flag '{token}' is not allowed.")
        elif argv[1] not in {"-v", "--version"}:
            raise ValidationError("Only PHP version flags and selected Artisan commands are allowed.")
    if base == "composer":
        if len(argv) < 2 or argv[1] not in {"install", "update", "dump-autoload", "dump-autoload", "show", "validate", "outdated"}:
            raise ValidationError("This Composer command is not allowed.")
    if base in {"python", "python3"}:
        if len(argv) >= 2 and argv[1] == "manage.py":
            if len(argv) < 3 or argv[2] not in {"migrate", "makemigrations", "createsuperuser", "collectstatic", "check"}:
                raise ValidationError("This Django manage.py command is not allowed.")
        elif len(argv) >= 2 and argv[1] in {"-c", "-m"}:
            raise ValidationError("Inline/eval Python execution is not allowed.")
        elif len(argv) >= 2 and not argv[1].startswith("-") and "/" in argv[1]:
            raise ValidationError("Python scripts must stay inside the work directory.")
    if base in {"npm", "yarn", "pnpm"}:
        if len(argv) < 2 or argv[1] not in {"install", "ci", "run", "test", "list", "outdated", "audit"}:
            raise ValidationError("This package-manager command is not allowed.")
        if argv[1] == "run" and len(argv) < 3:
            raise ValidationError("npm/yarn/pnpm run requires a script name.")
    if base == "npx" and (len(argv) < 2 or argv[1] not in {"vite", "tsc"}):
        raise ValidationError("Only approved npx tools are allowed.")
    if base in {"pip", "pip3"}:
        if len(argv) < 2 or argv[1] not in {"install", "list", "show", "freeze", "check"}:
            raise ValidationError("This pip command is not allowed.")


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


def create_session(service: Service, user, workdir: str | None = None) -> tuple[object, str]:
    platform = _platform_for_service(service)
    root = DEFAULT_WORKDIRS.get(platform, "/app")
    workdir = _safe_workdir(workdir or root, root)
    _resolve_container(service)
    now = timezone.now()
    # Lazy import avoids model cycle during Django app loading.
    from services.models import ShellSession
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
            expires_at=now + timedelta(minutes=SESSION_TTL_MINUTES),
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
    if session.expires_at <= now:
        ShellSession.objects.filter(pk=session.pk).update(status=ShellSession.Status.EXPIRED)
        raise ValidationError("Shell session expired.")
    return session


def _is_destructive_command(argv: list[str]) -> bool:
    if not argv:
        return False
    base = os.path.basename(argv[0])
    key = tuple(argv[:3])
    if key in DESTRUCTIVE_COMMANDS:
        return True
    if base in {"yarn", "pnpm"} and len(argv) >= 2 and tuple(argv[:2]) in DESTRUCTIVE_COMMANDS:
        return True
    return False


def command_catalog(platform: str) -> list[dict]:
    """Return UI-safe command metadata; custom arbitrary commands are excluded."""
    items = [
        {"command": c, "label": c.replace("_", " "), "mutating": False, "dangerous": False}
        for c in sorted(GENERIC_COMMAND_CATALOG)
    ]
    if platform in {"laravel", "php"}:
        items.extend(
            {"command": f"php artisan {name}", "label": meta["label"],
             "mutating": bool(meta.get("mutating")), "dangerous": bool(meta.get("destructive"))}
            for name, meta in sorted(ARTISAN_COMMAND_CATALOG.items())
        )
        items.extend([
            {"command": "php -v", "label": "PHP version", "mutating": False, "dangerous": False},
            {"command": "composer show", "label": "Composer packages", "mutating": False, "dangerous": False},
            {"command": "composer validate", "label": "Validate composer.json", "mutating": False, "dangerous": False},
        ])
    elif platform in {"django", "python"}:
        for cmd, label, mut in [
            ("python manage.py check", "Django system check", False),
            ("python manage.py migrate", "Run migrations", True),
            ("python manage.py makemigrations", "Create migrations", True),
            ("python manage.py createsuperuser", "Create Django superuser", True),
            ("python manage.py collectstatic", "Collect static files", True),
        ]:
            items.append({"command": cmd, "label": label, "mutating": mut, "dangerous": False})
        items += [
            {"command": "python --version", "label": "Python version", "mutating": False, "dangerous": False},
            {"command": "pip list", "label": "Installed Python packages", "mutating": False, "dangerous": False},
        ]
    elif platform == "node":
        items += [
            {"command": "node --version", "label": "Node version", "mutating": False, "dangerous": False},
            {"command": "npm list", "label": "Installed npm packages", "mutating": False, "dangerous": False},
            {"command": "npm run build", "label": "Run production build", "mutating": True, "dangerous": False},
            {"command": "npm test", "label": "Run tests", "mutating": False, "dangerous": False},
        ]
    return items


def execute_command(session, command: str, *, confirm: bool = False) -> dict:
    _reject_shell_syntax(command)
    argv = shlex.split(command, posix=True)
    _validate_platform_command(argv, session.platform, session.root_path)
    if _is_destructive_command(argv) and not confirm:
        raise ValidationError("This command changes application state. Re-submit it with confirm=true.")
    if argv and argv[0] == "cd":
        if len(argv) != 2:
            raise ValidationError("cd accepts exactly one path.")
        session.workdir = _safe_workdir(argv[1], session.root_path)
        session.last_used_at = timezone.now()
        session.save(update_fields=["workdir", "last_used_at"])
        return {"exit_code": 0, "stdout": session.workdir + "\n", "stderr": "", "cwd": session.workdir}
    container = _resolve_container(session.service)
    try:
        result = container.exec_run(argv, workdir=session.workdir, stdout=True, stderr=True, demux=True, tty=False)
    except APIError as exc:
        raise ValidationError(f"Docker exec failed: {exc}") from exc
    stdout, stderr = (b"", b"")
    if isinstance(result.output, tuple):
        stdout, stderr = result.output
    else:
        stdout = result.output or b""
    def clip(data):
        if isinstance(data, bytes):
            return data[:MAX_OUTPUT_BYTES].decode("utf-8", "replace")
        return str(data or "")[:MAX_OUTPUT_BYTES]
    session.last_used_at = timezone.now()
    session.expires_at = timezone.now() + timedelta(minutes=SESSION_TTL_MINUTES)
    session.save(update_fields=["last_used_at", "expires_at"])
    return {"exit_code": int(result.exit_code or 0), "stdout": clip(stdout), "stderr": clip(stderr), "cwd": session.workdir}


def close_session(session) -> None:
    session.status = session.Status.CLOSED
    session.closed_at = timezone.now()
    session.save(update_fields=["status", "closed_at"])
