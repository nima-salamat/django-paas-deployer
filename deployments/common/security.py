"""
deployments/common/security.py
------------------------------
Centralised security primitives reused across the deployment subsystem.

Goals:
  * Validate user-supplied paths so archives cannot escape their target
    directory (Zip Slip) and bind mounts cannot expose host paths.
  * Validate user-supplied command fragments so they cannot inject shell
    metacharacters into Dockerfile RUN lines or supervisord ``command=``
    directives.
  * Validate identifiers (container names, image tags, network names)
    against the Docker / supervisord accepted character set.

These helpers are pure functions with no Django or Docker imports so they
can be unit-tested in isolation.
"""

from __future__ import annotations

import os
import re
from typing import Iterable

from .exceptions import DeploymentSecurityError


# ---------------------------------------------------------------------------
# Path / archive safety
# ---------------------------------------------------------------------------

def is_safe_archive_name(name: str) -> bool:
    """
    Return True if ``name`` is a safe archive member path.

    Rejects:
      * absolute paths (leading ``/``)
      * parent traversal (``../`` prefix or ``/../`` substring)
      * empty / ``.`` / ``..``
      * Windows drive prefixes (``C:\\``)
    """
    if not name or name in (".", ".."):
        return False
    normalised = name.replace("\\", "/")
    if normalised.startswith("/"):
        return False
    if normalised.startswith("../"):
        return False
    if "/../" in normalised:
        return False
    if re.match(r"^[A-Za-z]:[\\/]", normalised):
        return False
    return True


def is_zip_symlink(zip_info) -> bool:
    """
    Return True if a ``zipfile.ZipInfo`` describes a symlink member.

    ``external_attr`` stores the UNIX mode in its upper 16 bits; symlinks
    use ``0o120000`` in the ``S_IFMT`` portion.
    """
    try:
        mode = (zip_info.external_attr >> 16) & 0o170000
        return mode == 0o120000
    except Exception:
        return False


def safe_join(base: str, member: str) -> str:
    """
    Join ``member`` onto ``base`` and assert the result is inside ``base``.

    Raises ``DeploymentSecurityError`` if the resolved path escapes ``base``.
    """
    abs_base = os.path.abspath(base)
    abs_target = os.path.abspath(os.path.join(abs_base, member))
    if abs_target != abs_base and not abs_target.startswith(abs_base + os.sep):
        raise DeploymentSecurityError(
            f"Unsafe path '{member}' escapes base directory.",
            details={"base": abs_base, "member": member, "resolved": abs_target},
        )
    return abs_target


# ---------------------------------------------------------------------------
# Host path policy for bind mounts
# ---------------------------------------------------------------------------

# Conservative default allow-list.  Operators may extend via
# ``settings.DEPLOYMENT_ALLOWED_BIND_PREFIXES``.
_DEFAULT_ALLOWED_BIND_PREFIXES: tuple[str, ...] = (
    "/srv/deployments/",
    "/var/lib/deployments/",
    "/opt/deployments/",
)


def get_allowed_bind_prefixes() -> tuple[str, ...]:
    """Read the configured allow-list of host paths for bind mounts."""
    try:
        from django.conf import settings  # type: ignore

        configured = getattr(settings, "DEPLOYMENT_ALLOWED_BIND_PREFIXES", None)
        if configured:
            return tuple(os.path.abspath(p) + os.sep for p in configured)
    except Exception:
        pass
    return tuple(os.path.abspath(p) + os.sep for p in _DEFAULT_ALLOWED_BIND_PREFIXES)


def validate_bind_source(source: str) -> str:
    """
    Validate a user-supplied bind-mount source path.

    Returns the abspath if it is inside one of the configured allow-list
    prefixes.  Raises ``DeploymentSecurityError`` otherwise.

    This is the single chokepoint that prevents a malicious user from
    bind-mounting ``/etc``, ``/var/run/docker.sock``, ``/root``, ``/`` etc.
    into their container.
    """
    if not source or not isinstance(source, str):
        raise DeploymentSecurityError("Empty bind-mount source.")
    normalised = os.path.abspath(source)
    allowed = get_allowed_bind_prefixes()
    if not any(normalised.startswith(prefix) for prefix in allowed):
        raise DeploymentSecurityError(
            f"Bind-mount source '{source}' is not inside any allowed prefix.",
            details={
                "source": source,
                "normalised": normalised,
                "allowed_prefixes": list(allowed),
            },
        )
    return normalised


# ---------------------------------------------------------------------------
# Identifier validation
# ---------------------------------------------------------------------------

# Docker accepts [a-zA-Z0-9][a-zA-Z0-9_.-]* for container/image/network names.
_DOCKER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

# supervisord program names must be a valid Python identifier-ish token.
_SUPERVISOR_PROGRAM_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Celery app module path: dotted Python module, optionally ``.attr``.
_CELERY_APP_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")

# Safe shell-token set for entrypoint overrides.  We intentionally reject
# shell metacharacters because supervisor's ``command=`` is parsed by sh.
_SHELL_TOKEN_RE = re.compile(r"^[A-Za-z0-9_@./:=,+~-]+$")


def validate_docker_name(name: str, *, field: str = "name") -> str:
    if not name or not isinstance(name, str):
        raise DeploymentSecurityError(f"Invalid {field}: empty.")
    if len(name) > 256:
        raise DeploymentSecurityError(f"Invalid {field}: too long.")
    if not _DOCKER_NAME_RE.match(name):
        raise DeploymentSecurityError(
            f"Invalid {field} '{name}': must match [a-zA-Z0-9][a-zA-Z0-9_.-]*.",
            details={field: name},
        )
    return name


def validate_celery_app(value: str) -> str:
    """
    Validate a user-supplied Celery app module path.

    Celery app names are interpolated into supervisord ``command=`` lines
    which are parsed by ``sh -c``.  A value like ``app; rm -rf /`` would
    therefore be a command-injection vector.  We restrict to dotted
    Python module paths.
    """
    if not value or not isinstance(value, str):
        raise DeploymentSecurityError("Empty celery_app override.")
    cleaned = value.strip()
    if not _CELERY_APP_RE.match(cleaned):
        raise DeploymentSecurityError(
            f"Invalid celery_app '{value}': must be a dotted Python module path.",
            details={"celery_app": value},
        )
    return cleaned


def validate_shell_command(value: str, *, max_len: int = 4096) -> str:
    """
    Validate a user-supplied shell command fragment for use in
    supervisord ``command=`` or Dockerfile ``CMD``.

    We reject anything containing shell metacharacters that could break
    out of the intended command.  Callers that need full shell power
    should write their own Dockerfile, not use the override.
    """
    if not value or not isinstance(value, str):
        raise DeploymentSecurityError("Empty shell command override.")
    cleaned = value.strip()
    if not cleaned:
        raise DeploymentSecurityError("Empty shell command override.")
    if len(cleaned) > max_len:
        raise DeploymentSecurityError(
            f"Shell command override too long ({len(cleaned)} > {max_len}).",
        )
    # Reject obvious shell metacharacters that supervisord would interpret.
    forbidden = (";", "&", "|", "$", "`", "(", ")", "<", ">", "\n", "\r",
                 "*", "?", "[", "]", "{", "}", "!", "#", "~", "=")
    if any(ch in cleaned for ch in forbidden):
        raise DeploymentSecurityError(
            f"Shell command override contains forbidden metacharacters: '{cleaned}'.",
            details={"command": cleaned},
        )
    return cleaned


def sanitize_route_name(name: str) -> str:
    """Sanitise a string for use as a Traefik router name (no backticks,
    no whitespace)."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", name or "").strip("-")
    if not cleaned:
        cleaned = "service"
    return cleaned[:128]




# ---------------------------------------------------------------------------
# Post-extract tree validation + log redaction
# ---------------------------------------------------------------------------

def assert_tree_under(root: str) -> list[str]:
    """
    Walk ``root`` and ensure every entry resolves under root with a safe
    relative name.  Returns list of relative paths found.

    Raises DeploymentSecurityError on the first escape or unsafe name.
    """
    root_abs = os.path.realpath(root)
    if not os.path.isdir(root_abs):
        raise DeploymentSecurityError(
            "Extraction root does not exist or is not a directory.",
            details={"root": root_abs},
        )
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root_abs):
        for d in list(dirnames):
            if d == ".." or (d or "").startswith("/"):
                raise DeploymentSecurityError(
                    f"Unsafe directory name in extract tree: {d!r}",
                    details={"path": os.path.join(dirpath, d)},
                )
        for name in list(dirnames) + list(filenames):
            full = os.path.join(dirpath, name)
            try:
                real = os.path.realpath(full)
            except OSError as exc:
                raise DeploymentSecurityError(
                    f"Cannot resolve path in extract tree: {full}",
                    details={"path": full, "error": str(exc)},
                ) from exc
            if real != root_abs and not real.startswith(root_abs + os.sep):
                raise DeploymentSecurityError(
                    "Extracted path escapes project root (possible zip-slip).",
                    details={"path": real, "root": root_abs},
                )
            rel = os.path.relpath(real, root_abs).replace("\\", "/")
            if rel != "." and not is_safe_archive_name(rel):
                raise DeploymentSecurityError(
                    f"Unsafe relative path after extract: {rel!r}",
                    details={"path": rel},
                )
            found.append(rel)
    return found


def validate_final_app_layout(project_root: str) -> None:
    """
    Post-extract gate: refuse trees that still contain path-escape segments.
    Call after every ZIP extract before image build.
    """
    assert_tree_under(project_root)


_SECRET_LINE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|mysql_pwd|"
    r"postgres_password|redis_password|oracle_pwd)\s*[=:]\s*\S+"
)


def redact_secrets(text: str, *, max_len: int = 120_000) -> str:
    """Best-effort redact of common secret patterns before persisting logs."""
    if not text:
        return ""
    out = _SECRET_LINE.sub(r"\1=***REDACTED***", text)
    if len(out) > max_len:
        out = "[truncated]\n" + out[-max_len:]
    return out

__all__ = [
    "is_safe_archive_name",
    "is_zip_symlink",
    "safe_join",
    "get_allowed_bind_prefixes",
    "validate_bind_source",
    "validate_docker_name",
    "validate_celery_app",
    "validate_shell_command",
    "sanitize_route_name",
    "assert_tree_under",
    "validate_final_app_layout",
    "redact_secrets",
]
