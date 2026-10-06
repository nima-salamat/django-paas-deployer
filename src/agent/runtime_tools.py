import os
"""First-class service-local tools exposed to PassDeployer Agents.

Tools are small wrappers around existing runtime boundaries. They do not call
PassDeployer over HTTP from inside the backend.
"""
from __future__ import annotations

import posixpath
import re
import shlex
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RuntimeTool:
    name: str
    title: str
    summary: str
    platforms: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ("shell.read",)
    mutating: bool = False
    input_schema: dict[str, Any] | None = None
    handler: Callable[..., dict[str, Any]] | None = None

    def applies_to(self, platform: str) -> bool:
        return not self.platforms or str(platform or "").lower() in set(self.platforms)

    def enabled_for(self, scopes: set[str], platform: str) -> bool:
        return self.applies_to(platform) and set(self.scopes).issubset(scopes)


def _safe_command_name(value: str) -> str:
    value = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.:+/@-]{1,64}", value):
        raise ValueError("Tool command names must be simple executable names.")
    return value


def _workspace_inspect(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import (
        _container_mount_policy,
        _platform_for_service,
        _resolve_container,
        default_workdir_for_platform,
        path_access,
        runtime_workdir_for_platform,
        shell_workspace_metadata,
    )

    container = _resolve_container(service)
    platform = _platform_for_service(service)
    restricted_root = default_workdir_for_platform(platform)
    runtime_root = runtime_workdir_for_platform(platform)
    root_ro, _mounts = _container_mount_policy(container)

    mount_rows = []
    for mount in container.attrs.get("Mounts") or []:
        destination = str(mount.get("Destination") or "").strip()
        if not destination.startswith("/"):
            continue
        mount_type = str(mount.get("Type") or "unknown").lower()
        mount_rows.append({
            "target": destination,
            "type": mount_type,
            "writable": bool(mount.get("RW", False)),
            "managed_volume": mount_type == "volume",
        })

    result = {
        "platform": platform,
        "restricted_workspace": restricted_root,
        "runtime_default_workdir": runtime_root,
        "container_rootfs_read_only": bool(root_ro),
        "mounts": sorted(mount_rows, key=lambda row: row["target"]),
        "notes": [
            "A Docker RW mount can still be non-writable to the runtime UID.",
            "A path outside the restricted workspace is not writable through restricted Shell.",
            "Developer Shell is broader, but still requires a safe container security posture.",
            "Control-plane configuration is not a runtime workspace.",
            "Persistent data may live on a volume while the application binary/configuration lives in the image.",
        ],
    }

    requested_paths = payload.get("paths") or []
    if not isinstance(requested_paths, list):
        raise ValueError("paths must be an array.")
    if len(requested_paths) > 32:
        raise ValueError("At most 32 paths can be inspected at once.")

    checks = []
    for raw_path in requested_paths:
        value = str(raw_path or "").strip()
        if not value:
            continue
        path = value if value.startswith("/") else posixpath.join(restricted_root, value)
        normalized = posixpath.normpath(path)
        within = (
            normalized == restricted_root
            or normalized.startswith(restricted_root.rstrip("/") + "/")
        )
        row = {
            "path": normalized,
            "inside_restricted_workspace": bool(within),
        }
        if not within:
            row["status"] = "outside_restricted_workspace"
            row["reason"] = "The restricted file/shell boundary will not expose this path."
            checks.append(row)
            continue

        access = path_access(container, normalized)
        row.update({
            "status": "writable" if access.get("effective_writable") else "not_writable",
            "mount_mode": access.get("mode"),
            "docker_mount_writable": bool(access.get("mount_writable")),
            "runtime_user_effective_writable": bool(access.get("effective_writable")),
            "runtime_writable": bool(access.get("writable")),
            "reason": access.get("reason"),
        })
        checks.append(row)

    result["paths"] = checks
    result["workspace_metadata"] = shell_workspace_metadata(service)
    return result


def _runtime_detect(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service, _resolve_container

    names = payload.get("commands")
    if names is None:
        names = [
            "php", "composer", "wp", "python", "pip", "node", "npm", "git",
            "mysql", "mariadb", "mysqladmin", "mariadb-admin", "psql",
            "pg_isready", "mongosh", "redis-cli", "sqlplus",
        ]
    if not isinstance(names, list):
        raise ValueError("commands must be an array.")
    if len(names) > 32:
        raise ValueError("At most 32 commands can be detected at once.")

    container = _resolve_container(service)
    rows = []
    for raw_name in names:
        name = _safe_command_name(raw_name)
        result = container.exec_run(
            ["/bin/sh", "-c", 'command -v "$1" 2>/dev/null || true', "probe", name],
            stdout=True,
            stderr=False,
            tty=False,
        )
        output = result.output if isinstance(result.output, (bytes, bytearray)) else b""
        matches = output.decode("utf-8", "replace").strip().splitlines()[-1:]
        rows.append({
            "command": name,
            "installed": bool(matches),
            "path": matches[0] if matches else None,
        })

    return {
        "platform": _platform_for_service(service),
        "commands": rows,
        "note": "Tool availability is runtime-specific; do not assume a binary exists only because the platform supports it.",
    }


def _php_lint(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import (
        _platform_for_service,
        _resolve_container,
        _run_argv_with_timeout,
        default_workdir_for_platform,
        validate_argv_for_container,
    )

    platform = _platform_for_service(service)
    if platform not in {"php", "laravel", "wordpress"}:
        raise ValueError("php.lint is only available for PHP, Laravel or WordPress services.")

    raw_path = str(payload.get("path") or "").strip()
    if not raw_path:
        raise ValueError("path is required.")

    root = default_workdir_for_platform(platform)
    path = raw_path if raw_path.startswith("/") else posixpath.join(root, raw_path)
    container = _resolve_container(service)
    argv = ["php", "-l", path]
    validate_argv_for_container(argv, platform, root, container)
    code, stdout, stderr = _run_argv_with_timeout(
        container, argv, posixpath.dirname(root) if root == "/" else root, timeout_seconds=60
    )
    return {
        "platform": platform,
        "path": path,
        "exit_code": code,
        "valid": code == 0,
        "stdout": stdout.decode("utf-8", "replace")[:65536],
        "stderr": stderr.decode("utf-8", "replace")[:65536],
    }




def _command_output_text(value):
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", "replace")
    return str(value or "")


def command_result_from_argv(service, user, argv: list[str], *, confirm: bool = False) -> dict[str, Any]:
    """Execute one validated tool command without creating a persistent shell session."""
    from services.shell import (
        _is_destructive_command,
        _platform_for_service,
        _resolve_container,
        _run_argv_with_timeout,
        _run_mutating_argv,
        classify_command_risk,
        default_workdir_for_platform,
        record_shell_audit,
        validate_argv_for_container,
    )

    platform = _platform_for_service(service)
    root = default_workdir_for_platform(platform)
    container = _resolve_container(service)
    validate_argv_for_container(argv, platform, root, container, allow_advanced=False)
    risk = classify_command_risk(argv)

    if _is_destructive_command(argv) and not confirm:
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": None,
            "cwd": root,
            "risk": risk,
            "requires_confirmation": True,
        }

    if os.path.basename(argv[0]).lower() in {"mkdir", "touch", "rm", "rmdir", "cp", "mv", "tee"}:
        code, stdout, stderr = _run_mutating_argv(container, argv, root)
    else:
        code, stdout, stderr = _run_argv_with_timeout(
            container, argv, root, timeout_seconds=120
        )

    result = {
        "stdout": _command_output_text(stdout)[:65536],
        "stderr": _command_output_text(stderr)[:65536],
        "exit_code": int(code),
        "cwd": root,
        "risk": risk,
    }
    try:
        record_shell_audit(
            service=service,
            user=user,
            action="tool_command",
            command=" ".join(shlex.quote(value) for value in argv),
            cwd=root,
            success=int(code) == 0,
            detail="runtime_tool",
            meta={"platform": platform, "risk": risk},
        )
    except Exception:
        pass
    return result
def _wordpress_wp_cli(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service, is_interactive_command
    from agent.errors import AgentError

    platform = _platform_for_service(service)
    if platform != "wordpress":
        raise ValueError("wordpress.wp_cli is only available for WordPress services.")

    args = payload.get("args") or []
    if not isinstance(args, list):
        raise ValueError("args must be an array.")
    if len(args) > 32:
        raise ValueError("At most 32 WP-CLI arguments are allowed per tool call.")

    argv = ["wp"] + [str(value) for value in args]
    if any("\n" in value or "\r" in value or "\x00" in value for value in argv):
        raise ValueError("WP-CLI arguments cannot contain control characters.")
    if is_interactive_command(argv):
        raise AgentError(
            "TOOL_REQUIRES_INTERACTIVE",
            "This WP-CLI operation requires the interactive PTY shell.",
            status_code=409,
            failure_domain="runtime",
            extra={
                "transport": "interactive_pty",
                "command": " ".join(shlex.quote(value) for value in argv),
            },
        )

    result = command_result_from_argv(
        service,
        user,
        argv,
        confirm=bool(payload.get("confirm", False)),
    )
    return {"platform": platform, "tool": "wp-cli", **result}


TOOLS = (
    RuntimeTool(
        name="workspace.inspect",
        title="Inspect workspace and mounts",
        summary="Tell the Agent which workspace is managed, which mounts exist, and whether requested paths are writable.",
        scopes=("shell.read",),
        input_schema={
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 32,
                }
            },
        },
        handler=_workspace_inspect,
    ),
    RuntimeTool(
        name="runtime.detect",
        title="Detect runtime tools",
        summary="Detect whether common framework and database CLIs actually exist in the running container.",
        scopes=("shell.read",),
        input_schema={
            "type": "object",
            "properties": {
                "commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 32,
                }
            },
        },
        handler=_runtime_detect,
    ),
    RuntimeTool(
        name="php.lint",
        title="Lint PHP file",
        summary="Run PHP syntax checking against one file inside the managed PHP workspace.",
        platforms=("php", "laravel", "wordpress"),
        scopes=("shell.read",),
        input_schema={
            "type": "object",
            "required": ["path"],
            "properties": {"path": {"type": "string"}},
        },
        handler=_php_lint,
    ),
    RuntimeTool(
        name="wordpress.wp_cli",
        title="Run WP-CLI",
        summary="Run a non-interactive, policy-checked WP-CLI operation against the WordPress site.",
        platforms=("wordpress",),
        scopes=("shell.execute",),
        mutating=True,
        input_schema={
            "type": "object",
            "required": ["args"],
            "properties": {
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 32,
                },
                "confirm": {"type": "boolean", "default": False},
            },
        },
        handler=_wordpress_wp_cli,
    ),
)


def tools_for_service(agent, service):
    from services.shell import _platform_for_service
    platform = _platform_for_service(service)
    scopes = set(agent.scopes or [])
    return [tool for tool in TOOLS if tool.enabled_for(scopes, platform)]


def tool_for_service(agent, service, name: str):
    return next(
        (tool for tool in tools_for_service(agent, service) if tool.name == str(name)),
        None,
    )


def serialize_tool(tool: RuntimeTool) -> dict[str, Any]:
    return {
        "name": tool.name,
        "title": tool.title,
        "summary": tool.summary,
        "platforms": list(tool.platforms),
        "required_scopes": list(tool.scopes),
        "mutating": bool(tool.mutating),
        "interactive": False,
        "input_schema": tool.input_schema or {"type": "object"},
    }
