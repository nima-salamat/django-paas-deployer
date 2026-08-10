"""
deployments/common/security.py
------------------------------
Central security primitives for the deployment pipeline.

All archive extraction, bind mounts, Docker names, and shell-ish
overrides MUST go through this module.  Fail closed: any violation
raises DeploymentSecurityError / DeploymentValidationError and the
deploy must stop.
"""

from __future__ import annotations

import os
import re
from typing import Iterable

from deployments.common.exceptions import (
    DeploymentSecurityError,
    DeploymentValidationError,
)

# ---------------------------------------------------------------------------
# Archive / path safety
# ---------------------------------------------------------------------------

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def is_safe_archive_name(name: str) -> bool:
    """
    Reject absolute paths, Windows drive letters, and any '..' segment.

    Used for every ZIP/TAR member name before extraction.
    """
    if not name or not str(name).strip():
        return False
    n = str(name).replace("\\", "/").strip()
    if n.startswith("/") or n.startswith("\\"):
        return False
    if _WINDOWS_DRIVE.match(n):
        return False
    parts = [p for p in n.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return False
    if n in (".", ".."):
        return False
    return True


def is_zip_symlink(zip_info) -> bool:
    """True when ZipInfo external_attr indicates a Unix symlink."""
    mode = (getattr(zip_info, "external_attr", 0) or 0) >> 16
    return (mode & 0o170000) == 0o120000


def safe_join(base: str, *paths: str) -> str:
    """
    Join paths and assert the result stays under ``base`` after realpath.

    Raises DeploymentSecurityError on escape (zip-slip).
    """
    base_abs = os.path.realpath(base)
    candidate = os.path.realpath(os.path.join(base_abs, *paths))
    if candidate != base_abs and not candidate.startswith(base_abs + os.sep):
        raise DeploymentSecurityError(
            "Path escapes the allowed extraction root.",
            stage="archive_validation",
            details={"base": base_abs, "candidate": candidate},
        )
    return candidate


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
            stage="archive_validation",
            details={"root": root_abs},
        )

    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root_abs):
        for d in list(dirnames):
            if d == ".." or d.startswith("/") or _WINDOWS_DRIVE.match(d or ""):
                raise DeploymentSecurityError(
                    f"Unsafe directory name in extract tree: {d!r}",
                    stage="archive_validation",
                    details={"path": os.path.join(dirpath, d)},
                )
        for name in list(dirnames) + list(filenames):
            full = os.path.join(dirpath, name)
            try:
                real = os.path.realpath(full)
            except OSError as exc:
                raise DeploymentSecurityError(
                    f"Cannot resolve path in extract tree: {full}",
                    stage="archive_validation",
                    details={"path": full, "error": str(exc)},
                ) from exc
            if real != root_abs and not real.startswith(root_abs + os.sep):
                raise DeploymentSecurityError(
                    "Extracted path escapes project root (possible zip-slip).",
                    stage="archive_validation",
                    details={"path": real, "root": root_abs},
                )
            rel = os.path.relpath(real, root_abs).replace("\\", "/")
            if rel != "." and not is_safe_archive_name(rel):
                raise DeploymentSecurityError(
                    f"Unsafe relative path after extract: {rel!r}",
                    stage="archive_validation",
                    details={"path": rel},
                )
            found.append(rel)
    return found


def validate_final_app_layout(project_root: str) -> None:
    """
    Post-extract gate: refuse trees that still contain path-escape
    segments.  Call after every ZIP extract before image build.
    """
    assert_tree_under(project_root)


# ---------------------------------------------------------------------------
# Bind mounts (host paths)
# ---------------------------------------------------------------------------

_DEFAULT_BIND_ALLOWLIST = (
    "/var/lib/paas/volumes",
    "/var/lib/paas/data",
    "/data/paas",
)


def _bind_allowlist() -> tuple[str, ...]:
    try:
        from django.conf import settings  # type: ignore

        extra = getattr(settings, "DEPLOYMENT_BIND_ALLOWLIST", None)
        if extra:
            return tuple(str(p) for p in extra)
    except Exception:
        pass
    return _DEFAULT_BIND_ALLOWLIST


def validate_bind_source(source: str) -> str:
    """
    Bind source must be absolute and under an allow-listed host prefix.
    Returns the realpath.  Fail closed.
    """
    if not source or not os.path.isabs(str(source)):
        raise DeploymentSecurityError(
            "Bind mount source must be an absolute path.",
            stage="volume",
            details={"source": source},
        )
    real = os.path.realpath(source)
    allowed = _bind_allowlist()
    if not any(
        real == a.rstrip("/") or real.startswith(a.rstrip("/") + os.sep)
        for a in allowed
    ):
        raise DeploymentSecurityError(
            "Bind mount source is outside the allowed host prefixes.",
            stage="volume",
            details={"source": real, "allowed": list(allowed)},
        )
    return real


# ---------------------------------------------------------------------------
# Docker identifiers / Traefik routes
# ---------------------------------------------------------------------------

_DOCKER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")
_ROUTE_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def validate_docker_name(name: str, *, field: str = "name") -> str:
    n = (name or "").strip().lower()
    if not n or not _DOCKER_NAME_RE.match(n):
        raise DeploymentValidationError(
            f"Invalid Docker {field}: {name!r}",
            stage="validation",
            details={field: name},
        )
    return n


def sanitize_route_name(name: str) -> str:
    n = re.sub(r"[^a-z0-9-]", "-", (name or "").lower())
    n = re.sub(r"-{2,}", "-", n).strip("-")
    if not n or not _ROUTE_RE.match(n):
        n = "app-" + re.sub(r"[^a-z0-9]", "", (name or "x").lower())[:20]
    return n[:63]


# ---------------------------------------------------------------------------
# Shell / supervisord safety
# ---------------------------------------------------------------------------

_SHELL_META = re.compile(r"[;|&`$<>(){}\n\r]")


def validate_shell_command(cmd: str, *, max_len: int = 512) -> str:
    """
    Allow a simple process argv string only — no shell metacharacters.
    Used for user-supplied entry_point overrides.
    """
    c = (cmd or "").strip()
    if not c or len(c) > max_len:
        raise DeploymentValidationError(
            "entry_point is empty or too long.",
            stage="validation",
        )
    if _SHELL_META.search(c):
        raise DeploymentSecurityError(
            "entry_point contains disallowed shell metacharacters.",
            stage="validation",
            details={"entry_point": c[:80]},
        )
    return c


def validate_celery_app(value: str) -> str:
    """Dotted Python path only (safe for supervisord command=)."""
    v = (value or "").strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", v):
        raise DeploymentSecurityError(
            "celery_app must be a dotted Python path only.",
            stage="validation",
            details={"celery_app": v[:80]},
        )
    return v


# ---------------------------------------------------------------------------
# Log redaction (container logs → DeployLog)
# ---------------------------------------------------------------------------

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
    "assert_tree_under",
    "validate_final_app_layout",
    "validate_bind_source",
    "validate_docker_name",
    "sanitize_route_name",
    "validate_shell_command",
    "validate_celery_app",
    "redact_secrets",
]
