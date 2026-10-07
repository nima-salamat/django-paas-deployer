"""First-class service-local tools exposed to PassDeployer Agents.

Tools are small wrappers around existing runtime boundaries. They do not call
PassDeployer over HTTP from inside the backend.
"""
from __future__ import annotations

import os

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
        from agent.errors import AgentError
        raise AgentError(
            "CONFIRMATION_REQUIRED",
            "This runtime tool operation is destructive and requires confirm=true.",
            status_code=409,
            failure_domain="authorization",
            extra={"tool_command": " ".join(shlex.quote(value) for value in argv), "risk": risk},
        )

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
    try:
        from agent.application import redact_shell_result
        result = redact_shell_result(service, result)
    except Exception:
        pass
    return result


def _run_tool_commands(service, user, commands: list[list[str]], *, continue_on_error: bool = True) -> list[dict[str, Any]]:
    results = []
    for argv in commands:
        try:
            result = command_result_from_argv(service, user, argv, confirm=False)
            results.append({"command": argv, **result})
        except Exception as exc:
            if not continue_on_error:
                raise
            results.append({"command": argv, "exit_code": None, "error": str(exc)})
    return results


def _wordpress_status(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service

    if _platform_for_service(service) != "wordpress":
        raise ValueError("wordpress.status is only available for WordPress services.")

    checks = _run_tool_commands(service, user, [
        ["wp", "--info"],
        ["wp", "core", "is-installed"],
        ["wp", "core", "version"],
        ["wp", "option", "get", "home"],
        ["wp", "option", "get", "siteurl"],
        ["wp", "option", "get", "blogname"],
        ["wp", "option", "get", "timezone_string"],
        ["wp", "db", "check"],
    ])

    def output(name: str) -> str:
        row = next((x for x in checks if " ".join(x["command"]) == name), None)
        return str((row or {}).get("stdout") or "").strip()

    installed_row = next(
        (x for x in checks if " ".join(x["command"]) == "wp core is-installed"),
        {},
    )
    installed = int(installed_row.get("exit_code") or 1) == 0
    cli_row = next((x for x in checks if " ".join(x["command"]) == "wp --info"), {})
    cli_available = int(cli_row.get("exit_code") or 1) == 0 and bool(cli_row.get("stdout"))

    return {
        "platform": "wordpress",
        "wp_cli_available": cli_available,
        "wp_cli_info": output("wp --info"),
        "installed": installed,
        "core_version": output("wp core version"),
        "home": output("wp option get home"),
        "siteurl": output("wp option get siteurl"),
        "site_title": output("wp option get blogname"),
        "timezone": output("wp option get timezone_string"),
        "database": next((x for x in checks if " ".join(x["command"]) == "wp db check"), {}),
        "checks": checks,
    }


def _wordpress_page_create(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service

    if _platform_for_service(service) != "wordpress":
        raise ValueError("wordpress.page.create is only available for WordPress services.")
    title = str(payload.get("title") or "").strip()
    content = str(payload.get("content") or "")
    if not title:
        raise ValueError("title is required.")
    if len(title) > 300 or len(content) > 256 * 1024:
        raise ValueError("Page title/content is too large.")
    status = str(payload.get("status") or "draft").strip().lower()
    if status not in {"draft", "publish", "pending", "private"}:
        raise ValueError("Unsupported page status.")
    args = ["wp", "post", "create", "--post_type=page", f"--post_title={title}", f"--post_content={content}", f"--post_status={status}", "--porcelain"]
    if payload.get("slug"):
        slug = str(payload["slug"]).strip()
        if not re.fullmatch(r"[a-z0-9-]{1,200}", slug):
            raise ValueError("slug must contain lowercase letters, digits and hyphens only.")
        args.append(f"--post_name={slug}")
    result = command_result_from_argv(service, user, args, confirm=bool(payload.get("confirm", False)))
    return {"platform": "wordpress", "title": title, "status": status, **result}


def _wordpress_page_update(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service

    if _platform_for_service(service) != "wordpress":
        raise ValueError("wordpress.page.update is only available for WordPress services.")
    try:
        page_id = int(payload.get("page_id"))
    except (TypeError, ValueError):
        raise ValueError("page_id must be an integer.")
    args = ["wp", "post", "update", str(page_id)]
    fields = 0
    if payload.get("title") is not None:
        title = str(payload.get("title") or "").strip()
        if not title or len(title) > 300:
            raise ValueError("title must be non-empty and at most 300 characters.")
        args.append(f"--post_title={title}")
        fields += 1
    if payload.get("content") is not None:
        content = str(payload.get("content") or "")
        if len(content) > 256 * 1024:
            raise ValueError("content is too large.")
        args.append(f"--post_content={content}")
        fields += 1
    if payload.get("status") is not None:
        status = str(payload.get("status") or "").strip().lower()
        if status not in {"draft", "publish", "pending", "private"}:
            raise ValueError("Unsupported page status.")
        args.append(f"--post_status={status}")
        fields += 1
    if payload.get("slug") is not None:
        slug = str(payload.get("slug") or "").strip()
        if not re.fullmatch(r"[a-z0-9-]{1,200}", slug):
            raise ValueError("slug must contain lowercase letters, digits and hyphens only.")
        args.append(f"--post_name={slug}")
        fields += 1
    if not fields:
        raise ValueError("At least one page field is required.")
    result = command_result_from_argv(service, user, args, confirm=bool(payload.get("confirm", False)))
    return {"platform": "wordpress", "page_id": page_id, **result}

def _wordpress_plugin_manage(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service

    if _platform_for_service(service) != "wordpress":
        raise ValueError("wordpress.plugin.manage is only available for WordPress services.")
    action = str(payload.get("action") or "").strip().lower()
    slug = str(payload.get("slug") or "").strip()
    if action not in {"install", "activate", "deactivate", "update", "delete"}:
        raise ValueError("action must be install, activate, deactivate, update or delete.")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", slug):
        raise ValueError("slug must be a WordPress plugin slug.")
    args = ["wp", "plugin", action, slug]
    if action == "install" and payload.get("activate", False):
        args.append("--activate")
    result = command_result_from_argv(service, user, args, confirm=bool(payload.get("confirm", False)))
    return {"platform": "wordpress", "action": action, "slug": slug, **result}


def _wordpress_theme_manage(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service

    if _platform_for_service(service) != "wordpress":
        raise ValueError("wordpress.theme.manage is only available for WordPress services.")
    action = str(payload.get("action") or "").strip().lower()
    slug = str(payload.get("slug") or "").strip()
    if action not in {"install", "activate", "update", "delete"}:
        raise ValueError("action must be install, activate, update or delete.")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", slug):
        raise ValueError("slug must be a WordPress theme slug.")
    args = ["wp", "theme", action, slug]
    if action == "install" and payload.get("activate", False):
        args.append("--activate")
    result = command_result_from_argv(service, user, args, confirm=bool(payload.get("confirm", False)))
    return {"platform": "wordpress", "action": action, "slug": slug, **result}


def _wordpress_cache_flush(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service

    if _platform_for_service(service) != "wordpress":
        raise ValueError("wordpress.cache.flush is only available for WordPress services.")
    result = command_result_from_argv(service, user, ["wp", "cache", "flush"], confirm=bool(payload.get("confirm", False)))
    return {"platform": "wordpress", **result}


def _php_composer(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service

    platform = _platform_for_service(service)
    if platform not in {"php", "laravel", "wordpress"}:
        raise ValueError("php.composer is only available for PHP-compatible services.")
    detected = _runtime_detect(service, user, {"commands": ["composer"]})
    if not detected["commands"][0]["installed"]:
        return {"platform": platform, "installed": False, "action": str(payload.get("action") or "validate")}
    action = str(payload.get("action") or "validate").strip().lower()
    allowed = {"validate", "show", "outdated", "install", "update"}
    if action not in allowed:
        raise ValueError("Unsupported Composer action.")
    args = ["composer", action]
    if action in {"install", "update"} and payload.get("no_dev") is True:
        args.append("--no-dev")
    result = command_result_from_argv(service, user, args, confirm=bool(payload.get("confirm", False)))
    return {"platform": platform, "action": action, "installed": True, **result}

def _database_health(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service, _resolve_container, _database_runtime_values, runtime_workdir_for_platform, prepare_interactive_exec_environment, DATABASE_PLATFORMS

    platform = _platform_for_service(service)
    if platform not in {"mysql", "mariadb", "postgresql", "mongodb", "redis", "oracle"}:
        raise ValueError("database.health is only available for managed database runtimes.")
    container = _resolve_container(service)
    values = _database_runtime_values(service)
    env = prepare_interactive_exec_environment(container, platform=platform, root_path=runtime_workdir_for_platform(platform), service=service)
    username = str(values.get("username") or "").strip()
    database = str(values.get("database") or "").strip()
    port = str(values.get("port") or "").strip()
    if platform == "mysql":
        argv = ["mysqladmin", "--host=127.0.0.1", "--protocol=tcp", "ping"]
        if username: argv.insert(1, f"--user={username}")
    elif platform == "mariadb":
        argv = ["mariadb-admin", "--host=127.0.0.1", "--protocol=tcp", "ping"]
        if username: argv.insert(1, f"--user={username}")
    elif platform == "postgresql":
        argv = ["pg_isready", "-h", "127.0.0.1"]
        if port: argv += ["-p", port]
        if username: argv += ["-U", username]
        if database: argv += ["-d", database]
    elif platform == "redis":
        argv = ["redis-cli", "-h", "127.0.0.1", "ping"]
    elif platform == "mongodb":
        argv = ["mongosh", "--host", "127.0.0.1", "--quiet", "--eval", "db.adminCommand({ ping: 1 }).ok"]
    else:
        return {"platform": platform, "healthy": None, "status": "interactive_check_required", "client": "sqlplus"}
    result = container.exec_run(argv, workdir=runtime_workdir_for_platform(platform), environment=env, stdout=True, stderr=True, demux=True, tty=False)
    out, err = result.output if isinstance(result.output, tuple) else (result.output or b"", b"")
    code = int(result.exit_code if result.exit_code is not None else 1)
    return {
        "platform": platform,
        "healthy": code == 0,
        "exit_code": code,
        "stdout": _command_output_text(out)[:65536],
        "stderr": _command_output_text(err)[:65536],
        "client": DATABASE_PLATFORMS.get(platform, {}).get("client"),
    }

def _wordpress_core_update(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service

    if _platform_for_service(service) != "wordpress":
        raise ValueError("wordpress.core.update is only available for WordPress services.")

    args = ["wp", "core", "update"]
    version = str(payload.get("version") or "").strip()
    if version:
        if not re.fullmatch(r"[0-9]+\\.[0-9]+(?:\\.[0-9]+)?", version):
            raise ValueError("version must be a semantic WordPress version such as 7.1.2.")
        args.append(f"--version={version}")
    if payload.get("dry_run") is True:
        args.append("--dry-run")

    result = command_result_from_argv(
        service,
        user,
        args,
        confirm=bool(payload.get("confirm", False)),
    )
    return {"platform": "wordpress", "action": "core.update", **result}


def _wordpress_cron_run(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service

    if _platform_for_service(service) != "wordpress":
        raise ValueError("wordpress.cron.run is only available for WordPress services.")

    result = command_result_from_argv(
        service,
        user,
        ["wp", "cron", "event", "run", "--due-now"],
        confirm=bool(payload.get("confirm", False)),
    )
    return {"platform": "wordpress", "action": "cron.run", **result}


def _wordpress_site_configure(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service

    if _platform_for_service(service) != "wordpress":
        raise ValueError("wordpress.site.configure is only available for WordPress services.")

    commands = []
    changed = {}
    if payload.get("title") is not None:
        title = str(payload.get("title") or "").strip()
        if not title or len(title) > 300:
            raise ValueError("title must be between 1 and 300 characters.")
        commands.append(["wp", "option", "update", "blogname", title])
        changed["title"] = title
    if payload.get("timezone") is not None:
        timezone = str(payload.get("timezone") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_+./:-]{1,100}", timezone):
            raise ValueError("Invalid timezone.")
        commands.append(["wp", "option", "update", "timezone_string", timezone])
        changed["timezone"] = timezone
    if payload.get("locale") is not None:
        locale = str(payload.get("locale") or "").strip()
        if not re.fullmatch(r"[A-Za-z_]{2,20}", locale):
            raise ValueError("Invalid locale.")
        commands.append(["wp", "option", "update", "WPLANG", locale])
        changed["locale"] = locale
    if payload.get("permalink_structure") is not None:
        structure = str(payload.get("permalink_structure") or "").strip()
        if not re.fullmatch(r"/[A-Za-z0-9_%./-]{1,120}/", structure):
            raise ValueError("Invalid permalink structure.")
        commands.append(["wp", "rewrite", "structure", structure])
        changed["permalink_structure"] = structure
    if not commands:
        raise ValueError("At least one site setting is required.")

    results = []
    for argv in commands:
        results.append({
            "command": argv,
            **command_result_from_argv(
                service,
                user,
                argv,
                confirm=bool(payload.get("confirm", False)),
            ),
        })
    return {"platform": "wordpress", "action": "site.configure", "changed": changed, "results": results}


def _wordpress_search_replace(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service

    if _platform_for_service(service) != "wordpress":
        raise ValueError("wordpress.search_replace is only available for WordPress services.")

    old = str(payload.get("old") or "")
    new = str(payload.get("new") or "")
    if not old:
        raise ValueError("old is required.")
    if len(old) > 4096 or len(new) > 4096:
        raise ValueError("search/replace values are too large.")

    dry_run = bool(payload.get("dry_run", True))
    args = [
        "wp",
        "search-replace",
        old,
        new,
        "--all-tables-with-prefix",
        "--report-changed-only",
    ]
    if dry_run:
        args.append("--dry-run")
    result = command_result_from_argv(
        service,
        user,
        args,
        confirm=bool(payload.get("confirm", False)),
    )
    return {"platform": "wordpress", "action": "search-replace", "dry_run": dry_run, **result}


def _wordpress_scale(service, user, payload: dict[str, Any]) -> dict[str, Any]:
    from services.shell import _platform_for_service

    if _platform_for_service(service) != "wordpress":
        raise ValueError("wordpress.scale is only available for WordPress services.")

    try:
        replicas = int(payload.get("replicas"))
    except (TypeError, ValueError) as exc:
        raise ValueError("replicas must be an integer.") from exc
    if not 1 <= replicas <= 8:
        raise ValueError("replicas must be between 1 and 8.")

    from services.revisioning import scale_service_process
    revision, previous, current = scale_service_process(
        service,
        "web",
        replicas,
        created_by=user,
    )
    return {
        "platform": "wordpress",
        "action": "scale",
        "process": "web",
        "previous_replicas": previous,
        "replicas": current,
        "revision": {
            "id": str(revision.pk),
            "revision": revision.revision_number,
        },
    }


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
        name="wordpress.status",
        title="Inspect WordPress runtime",
        summary="Return WordPress installation state, WP-CLI availability, URLs, site settings and database health.",
        platforms=("wordpress",),
        scopes=("shell.read",),
        input_schema={"type": "object", "properties": {}},
        handler=_wordpress_status,
    ),
    RuntimeTool(
        name="wordpress.core.update",
        title="Update WordPress core",
        summary="Update WordPress core through WP-CLI, optionally pinning an exact semantic version.",
        platforms=("wordpress",),
        scopes=("shell.execute",),
        mutating=True,
        input_schema={
            "type": "object",
            "properties": {
                "version": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
                "confirm": {"type": "boolean", "default": False},
            },
        },
        handler=_wordpress_core_update,
    ),
    RuntimeTool(
        name="wordpress.cron.run",
        title="Run due WordPress cron",
        summary="Execute due WordPress cron events through WP-CLI.",
        platforms=("wordpress",),
        scopes=("shell.execute",),
        mutating=True,
        input_schema={"type": "object", "properties": {"confirm": {"type": "boolean", "default": False}}},
        handler=_wordpress_cron_run,
    ),
    RuntimeTool(
        name="wordpress.site.configure",
        title="Configure WordPress site",
        summary="Update supported site options such as title, timezone, locale and permalinks.",
        platforms=("wordpress",),
        scopes=("shell.execute",),
        mutating=True,
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "timezone": {"type": "string"},
                "locale": {"type": "string"},
                "permalink_structure": {"type": "string"},
                "confirm": {"type": "boolean", "default": False},
            },
        },
        handler=_wordpress_site_configure,
    ),
    RuntimeTool(
        name="wordpress.search_replace",
        title="Search and replace WordPress",
        summary="Run WP-CLI search-replace across tables using a dry-run by default.",
        platforms=("wordpress",),
        scopes=("shell.execute",),
        mutating=True,
        input_schema={
            "type": "object",
            "required": ["old", "new"],
            "properties": {
                "old": {"type": "string"},
                "new": {"type": "string"},
                "dry_run": {"type": "boolean", "default": True},
                "confirm": {"type": "boolean", "default": False},
            },
        },
        handler=_wordpress_search_replace,
    ),
    RuntimeTool(
        name="wordpress.scale",
        title="Scale WordPress web replicas",
        summary="Scale the WordPress web process to 1-8 Swarm replicas and persist the change as an immutable revision.",
        platforms=("wordpress",),
        scopes=("services.update",),
        mutating=True,
        input_schema={
            "type": "object",
            "required": ["replicas"],
            "properties": {"replicas": {"type": "integer", "minimum": 1, "maximum": 8}},
        },
        handler=_wordpress_scale,
    ),
    RuntimeTool(
        name="wordpress.inspect",
        title="Inspect WordPress site",
        summary="Return structured WordPress core, URL, active theme, active plugins and database health information.",
        platforms=("wordpress",),
        scopes=("shell.read",),
        input_schema={"type": "object", "properties": {}},
        handler=_wordpress_inspect,
    ),
    RuntimeTool(
        name="wordpress.page.create",
        title="Create WordPress page",
        summary="Create a WordPress Page through WP-CLI with structured title/content/status arguments.",
        platforms=("wordpress",),
        scopes=("shell.execute",),
        mutating=True,
        input_schema={
            "type": "object",
            "required": ["title"],
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "slug": {"type": "string"},
                "status": {"type": "string", "enum": ["draft", "publish", "pending", "private"]},
                "confirm": {"type": "boolean", "default": False},
            },
        },
        handler=_wordpress_page_create,
    ),
    RuntimeTool(
        name="wordpress.page.update",
        title="Update WordPress page",
        summary="Update a WordPress Page through WP-CLI using structured page fields.",
        platforms=("wordpress",),
        scopes=("shell.execute",),
        mutating=True,
        input_schema={"type": "object", "required": ["page_id"], "properties": {"page_id": {"type": "integer"}, "title": {"type": "string"}, "content": {"type": "string"}, "slug": {"type": "string"}, "status": {"type": "string", "enum": ["draft", "publish", "pending", "private"]}, "confirm": {"type": "boolean"}}},
        handler=_wordpress_page_update,
    ),
    RuntimeTool(
        name="wordpress.plugin.manage",
        title="Manage WordPress plugin",
        summary="Install, activate, deactivate, update or delete a plugin by slug.",
        platforms=("wordpress",),
        scopes=("shell.execute",),
        mutating=True,
        input_schema={"type": "object", "required": ["action", "slug"], "properties": {"action": {"type": "string", "enum": ["install", "activate", "deactivate", "update", "delete"]}, "slug": {"type": "string"}, "activate": {"type": "boolean", "default": False}, "confirm": {"type": "boolean"}}},
        handler=_wordpress_plugin_manage,
    ),
    RuntimeTool(
        name="wordpress.theme.manage",
        title="Manage WordPress theme",
        summary="Install, activate, update or delete a theme by slug.",
        platforms=("wordpress",),
        scopes=("shell.execute",),
        mutating=True,
        input_schema={"type": "object", "required": ["action", "slug"], "properties": {"action": {"type": "string", "enum": ["install", "activate", "update", "delete"]}, "slug": {"type": "string"}, "activate": {"type": "boolean", "default": False}, "confirm": {"type": "boolean"}}},
        handler=_wordpress_theme_manage,
    ),
    RuntimeTool(
        name="wordpress.cache.flush",
        title="Flush WordPress cache",
        summary="Flush the WordPress object cache through WP-CLI.",
        platforms=("wordpress",),
        scopes=("shell.execute",),
        mutating=True,
        input_schema={"type": "object", "properties": {"confirm": {"type": "boolean", "default": False}}},
        handler=_wordpress_cache_flush,
    ),
    RuntimeTool(
        name="php.composer",
        title="Run Composer action",
        summary="Run a constrained Composer action for PHP-compatible services.",
        platforms=("php", "laravel", "wordpress"),
        scopes=("shell.execute",),
        mutating=True,
        input_schema={"type": "object", "properties": {"action": {"type": "string", "enum": ["validate", "show", "outdated", "install", "update"]}, "no_dev": {"type": "boolean"}, "confirm": {"type": "boolean"}}},
        handler=_php_composer,
    ),
    RuntimeTool(
        name="database.health",
        title="Check database health",
        summary="Run an engine-native local readiness/health check without accepting arbitrary SQL or remote targets.",
        platforms=("mysql", "mariadb", "postgresql", "mongodb", "redis", "oracle"),
        scopes=("shell.read",),
        input_schema={"type": "object", "properties": {}},
        handler=_database_health,
    ),    RuntimeTool(
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
        scopes=("shell.execute", "shell.developer"),
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
