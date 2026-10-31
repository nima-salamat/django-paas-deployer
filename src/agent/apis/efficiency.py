"""Efficient Agent workflows: conditional context, batched workspace and MCP."""
from __future__ import annotations

import hashlib
import json
import re
from difflib import unified_diff
from urllib.parse import urlsplit

from django.conf import settings
from rest_framework.response import Response

from .base import AgentSecuredAPIView, idempotent
from ..application import RequestProxy, call_api_view_handler, get_service, redact_shell_result, service_payload
from ..errors import AgentError

MCP_PROTOCOL_VERSION = "2026-07-28"
MCP_LEGACY_PROTOCOL_VERSION = "2025-11-25"
MCP_SUPPORTED_VERSIONS = (MCP_PROTOCOL_VERSION, MCP_LEGACY_PROTOCOL_VERSION)


def _require_scope(agent, scope):
    if scope not in set(agent.scopes or []):
        raise AgentError("INSUFFICIENT_SCOPE", f"Missing required scope: {scope}.", status_code=403,
                         failure_domain="authorization", extra={"missing_scopes": [scope]})


def _shell_token(request, payload=None):
    payload = payload or {}
    token = request.headers.get("X-Shell-Token") or payload.get("shell_token") or payload.get("token")
    if not token:
        raise AgentError("SHELL_TOKEN_REQUIRED", "Create a shell session and send its temporary token in X-Shell-Token.",
                         status_code=401, failure_domain="authentication")
    return str(token)


def _file_operation(request, service_id, action, path, **values):
    from services.api.shell import shell_file_apiview
    token = _shell_token(request, getattr(request, "data", {}))
    data = {"action": action, "path": path, "token": token}
    data.update({k: v for k, v in values.items() if k not in {"token", "shell_token"}})
    return call_api_view_handler(shell_file_apiview, request, "post", service_id, data=data)


def _payload(response):
    value = getattr(response, "data", None)
    return value if isinstance(value, dict) else {"result": "error", "detail": "Invalid file operation response."}


def _paths(value, maximum=30):
    if not isinstance(value, list) or not value or len(value) > maximum:
        raise AgentError("INVALID_PATHS", f"paths must contain 1 to {maximum} entries.", status_code=400)
    result = []
    for raw in value:
        path = str(raw or "").strip()
        if not path or len(path) > 1024 or "\x00" in path:
            raise AgentError("INVALID_PATH", "Each path must be non-empty and shorter than 1024 characters.", status_code=400)
        result.append(path)
    return result


def _etag_response(request, payload, max_age=30):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    etag = '"' + hashlib.sha256(raw).hexdigest() + '"'
    response = Response(status=304) if request.headers.get("If-None-Match", "").strip() in {etag, "*"} else Response(payload)
    response["ETag"] = etag
    response["Cache-Control"] = f"private, max-age={max_age}, must-revalidate"
    response["Vary"] = "Authorization"
    return response


class AgentContextView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/context"
    audit_action = "agent.context.read"

    def get(self, request):
        from .identity import AgentCapabilitiesView
        from ..skills import skills_for_agent, skill_url
        from ..manifest import api_base_url

        base = api_base_url(request).rstrip("/")
        caps = AgentCapabilitiesView().get(request).data
        skills = skills_for_agent(request.agent)
        include = {
            item.strip().lower()
            for item in str(request.query_params.get("include") or "").split(",")
            if item.strip()
        }
        payload = {
            "result": "success",
            "api_version": "v1",
            "agent": {"id": str(request.agent.pk), "name": request.agent.name,
                      "scopes": sorted(request.agent.scopes or [])},
            "capabilities": caps,
            "links": {"openapi": f"{base}/openapi.json", "skills": f"{base}/skills",
                      "services": f"{base}/services", "mcp_protocol": MCP_PROTOCOL_VERSION},
            "skills": [{"name": item.name, "title": item.title, "summary": item.summary,
                        "url": skill_url(base, item)} for item in skills],
            "included": [],
            "omitted": [],
            "cache": {"etag": True, "max_age_seconds": 30},
        }
        if "services" in include:
            if "services.read" in set(request.agent.scopes or []):
                from .services import ServiceListCreateView
                service_response = _invoke_agent_view(ServiceListCreateView, "get", request)
                payload["services"] = getattr(service_response, "data", {})
                payload["included"].append("services")
                payload["cache"]["max_age_seconds"] = 5
            else:
                payload["omitted"].append({"name": "services", "reason": "missing_scope:services.read"})
        return _etag_response(request, payload, max_age=payload["cache"]["max_age_seconds"])


class WorkspaceTreeView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/workspace/tree"
    audit_action = "workspace.tree"
    audit_resource_type = "service"

    def get(self, request, service_id):
        _require_scope(request.agent, "shell.files.read")
        service = get_service(service_id, request.user, action="can_shell")
        from services.shell import authenticate_session, _resolve_container, _safe_workdir
        from services.api.shell import _assert_managed_target_safe

        params = getattr(request, "query_params", {}) or {}
        data = getattr(request, "data", {}) or {}
        session = authenticate_session(service, request.user, _shell_token(request, data))
        path = _safe_workdir(params.get("path") or data.get("path") or ".", session.root_path)
        container = _resolve_container(service)
        safe_path = _assert_managed_target_safe(container, path, session.root_path)
        try:
            depth = max(1, min(int(params.get("depth") or data.get("depth") or 3), 8))
            limit = max(1, min(int(params.get("limit") or data.get("limit") or 500), 1000))
            offset = max(0, int(params.get("offset") or data.get("offset") or 0))
        except (TypeError, ValueError):
            raise AgentError("INVALID_REQUEST", "depth, limit and offset must be integers.", status_code=400)
        entries = []
        for kind, flag in (("directory", "d"), ("file", "f")):
            result = container.exec_run(
                ["find", safe_path, "-mindepth", "1", "-maxdepth", str(depth), "-type", flag, "-print"],
                workdir=session.workdir, stdout=True, stderr=True, tty=False)
            output = result.output if isinstance(result.output, (bytes, bytearray)) else b""
            if int(getattr(result, "exit_code", 1) or 0) != 0:
                detail = getattr(result, "stderr", b"") or b""
                raise AgentError("WORKSPACE_TREE_FAILED", bytes(detail).decode("utf-8", "replace")[:1000] or
                                 "Unable to list workspace directory.", status_code=400, failure_domain="runtime")
            for item in bytes(output).decode("utf-8", "replace").splitlines():
                item = item.strip()
                if item:
                    relative = item[len(safe_path):].lstrip("/") if item.startswith(safe_path.rstrip("/") + "/") else item
                    entries.append({"path": relative, "kind": kind})
        entries.sort(key=lambda row: (row["path"].lower(), row["kind"]))
        payload = {"result": "success", "service_id": str(service.pk), "path": safe_path,
                   "depth": depth, "count": len(entries), "offset": offset, "limit": limit,
                   "next_offset": offset + limit if offset + limit < len(entries) else None,
                   "entries": entries[offset:offset + limit]}
        return _etag_response(request, payload, max_age=5)


class WorkspaceReadManyView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/workspace/read-many"
    audit_action = "workspace.read_many"
    audit_resource_type = "service"

    def post(self, request, service_id):
        _require_scope(request.agent, "shell.files.read")
        get_service(service_id, request.user, action="can_shell")
        paths = _paths(request.data.get("paths"))
        try:
            limit = min(max(int(request.data.get("max_total_bytes") or 1048576), 1024), 2097152)
            start = max(1, int(request.data["start_line"])) if request.data.get("start_line") is not None else None
            end = max(1, int(request.data["end_line"])) if request.data.get("end_line") is not None else None
        except (TypeError, ValueError):
            raise AgentError("INVALID_REQUEST", "Line and byte limits must be integers.", status_code=400)
        total, results = 0, []
        for path in paths:
            response = _file_operation(request, service_id, "read", path)
            item = _payload(response)
            if response.status_code >= 400 or item.get("result") == "error":
                results.append({"path": path, "ok": False, "status": response.status_code, "error": item})
                continue
            original = str(item.get("content") or "")
            is_truncated = bool(item.get("content_truncated"))
            digest = item.get("content_sha256")
            if is_truncated:
                results.append({"path": path, "ok": False,
                                "content_truncated": True,
                                "content_bytes": item.get("content_bytes"),
                                "error": {"code": "FILE_TOO_LARGE",
                                          "detail": "The managed file reader returned a truncated preview. Use a smaller file or a line-range read before patching."}})
                continue
            if item.get("content_utf8") is False:
                results.append({"path": path, "ok": False,
                                "error": {"code": "FILE_NOT_TEXT",
                                          "detail": "The file is not valid UTF-8 text; use a binary-safe upload or download workflow."}})
                continue
            digest = str(digest or hashlib.sha256(original.encode("utf-8")).hexdigest())
            content = original
            if start is not None or end is not None:
                content = "".join(content.splitlines(keepends=True)[(start or 1) - 1:end])
            size = len(content.encode("utf-8"))
            if total + size > limit:
                results.append({"path": path, "ok": False, "error": {"code": "BATCH_OUTPUT_LIMIT",
                                "detail": "Combined content limit reached; request fewer or smaller files."}})
                continue
            total += size
            results.append({"path": path, "ok": True, "content": content, "sha256": digest,
                            "content_bytes": item.get("content_bytes", len(original.encode("utf-8"))),
                            "bytes": size, "line_count": len(content.splitlines()),
                            "writable": bool(item.get("writable")),
                            "mount_writable": bool(item.get("mount_writable")),
                            "effective_writable": bool(item.get("effective_writable"))})
        self.audit_metadata = {"file_count": len(paths), "returned_bytes": total}
        return Response({"result": "success", "service_id": str(service_id), "files": results,
                         "returned_bytes": total})


class WorkspaceWriteManyView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/workspace/write-many"
    audit_action = "workspace.write_many"
    audit_resource_type = "service"
    audit_mutating = True

    @idempotent
    def post(self, request, service_id):
        _require_scope(request.agent, "shell.files.write")
        get_service(service_id, request.user, action="can_shell")
        files = request.data.get("files")
        if not isinstance(files, list) or not files or len(files) > 20:
            raise AgentError("INVALID_REQUEST", "files must contain 1 to 20 entries.", status_code=400)
        total, results = 0, []
        for item in files:
            if not isinstance(item, dict):
                results.append({"ok": False, "error": "File entry must be an object."})
                continue
            path, content = str(item.get("path") or "").strip(), item.get("content")
            if not path or not isinstance(content, str):
                results.append({"path": path, "ok": False, "error": "path and string content are required."})
                continue
            size = len(content.encode("utf-8"))
            total += size
            if size > 262144 or total > 2097152:
                results.append({"path": path, "ok": False, "error": "Per-file 256 KiB or batch 2 MiB limit exceeded."})
                continue
            expected = str(item.get("expected_sha256") or "").lower().strip()
            if expected:
                current_response = _file_operation(request, service_id, "read", path)
                current = _payload(current_response)
                current_hash = str(current.get("content_sha256") or "")
                if current.get("content_truncated"):
                    results.append({"path": path, "ok": False, "error": {"code": "FILE_TOO_LARGE",
                                    "detail": "The current file cannot be safely compared by the managed text editor."}})
                    continue
                if current.get("content_utf8") is False:
                    results.append({"path": path, "ok": False, "error": {"code": "FILE_NOT_TEXT",
                                    "detail": "The current file is not valid UTF-8 text."}})
                    continue
                if not current_hash:
                    current_hash = hashlib.sha256(str(current.get("content") or "").encode("utf-8")).hexdigest()
                if current_response.status_code >= 400 or current.get("result") == "error" or current_hash != expected:
                    results.append({"path": path, "ok": False, "error": {"code": "FILE_CONFLICT",
                                    "detail": "The file changed since it was read.", "current_sha256": current_hash}})
                    continue
            response = _file_operation(request, service_id, "write", path, content=content)
            outcome = _payload(response)
            results.append({"path": path, "ok": response.status_code < 400 and outcome.get("result") != "error",
                            "status": response.status_code, "result": outcome})
        self.audit_metadata = {"file_count": len(files), "content_bytes": total}
        return Response({"result": "success", "service_id": str(service_id), "files": results,
                         "written": sum(bool(row.get("ok")) for row in results),
                         "failed": sum(not bool(row.get("ok")) for row in results)})


class WorkspacePatchView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/workspace/patch"
    audit_action = "workspace.patch"
    audit_resource_type = "service"
    audit_mutating = True

    @idempotent
    def post(self, request, service_id):
        _require_scope(request.agent, "shell.files.write")
        get_service(service_id, request.user, action="can_shell")
        path = str(request.data.get("path") or "").strip()
        expected = str(request.data.get("expected_sha256") or "").lower().strip()
        changes = request.data.get("changes")
        if not path or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise AgentError("INVALID_REQUEST", "path and a SHA256 expected_sha256 are required.", status_code=400)
        if not isinstance(changes, list) or not changes or len(changes) > 50:
            raise AgentError("INVALID_REQUEST", "changes must contain 1 to 50 find/replace operations.", status_code=400)
        if sum(len(str(change).encode("utf-8")) for change in changes) > 262144:
            raise AgentError("PATCH_TOO_LARGE", "Patch input exceeds 256 KiB.", status_code=413)
        current = _payload(_file_operation(request, service_id, "read", path))
        if current.get("result") != "success":
            raise AgentError("FILE_READ_FAILED", current.get("detail") or "Unable to read file.", status_code=400,
                             failure_domain="runtime")
        if current.get("content_truncated"):
            raise AgentError("FILE_TOO_LARGE", "The current file exceeds the managed editor read limit; refusing to patch a truncated preview.",
                             status_code=413, failure_domain="storage",
                             extra={"content_bytes": current.get("content_bytes")})
        if current.get("content_utf8") is False:
            raise AgentError("FILE_NOT_TEXT", "The current file is not valid UTF-8 text; refusing a text patch.",
                             status_code=415, failure_domain="request")
        original = str(current.get("content") or "")
        current_hash = str(current.get("content_sha256") or hashlib.sha256(original.encode("utf-8")).hexdigest())
        if current_hash != expected:
            raise AgentError("FILE_CONFLICT", "File changed since it was read; fetch it again before patching.",
                             status_code=409, failure_domain="conflict",
                             extra={"expected_sha256": expected, "current_sha256": current_hash})
        updated = original
        for index, change in enumerate(changes):
            if not isinstance(change, dict) or not isinstance(change.get("find"), str) or not isinstance(change.get("replace"), str):
                raise AgentError("INVALID_PATCH", f"Change {index} requires string find and replace values.", status_code=400)
            needle = change["find"]
            count = int(change.get("expected_count", 1))
            actual = updated.count(needle)
            if not needle or count < 1 or actual != count:
                raise AgentError("PATCH_CONTEXT_MISMATCH", f"Change {index} expected {count} match(es), found {actual}.",
                                 status_code=409, failure_domain="conflict",
                                 extra={"change_index": index, "expected_count": count, "actual_count": actual})
            updated = updated.replace(needle, change["replace"])
        new_hash = hashlib.sha256(updated.encode("utf-8")).hexdigest()
        raw_diff = "".join(unified_diff(original.splitlines(True), updated.splitlines(True),
                                        fromfile=path, tofile=path))
        diff = raw_diff[:65536]
        diff_truncated = len(raw_diff) > len(diff)
        if request.data.get("dry_run", True) is True or request.data.get("apply") is not True:
            return Response({"result": "success", "dry_run": True, "applied": False, "path": path,
                             "old_sha256": current_hash, "new_sha256": new_hash, "diff": diff,
                             "diff_truncated": diff_truncated})
        response = _file_operation(request, service_id, "write", path, content=updated)
        outcome = _payload(response)
        if response.status_code >= 400 or outcome.get("result") == "error":
            raise AgentError("PATCH_WRITE_FAILED", outcome.get("detail") or "Unable to write patched file.",
                             status_code=400, failure_domain="runtime")
        self.audit_metadata = {"path": path, "old_sha256": current_hash, "new_sha256": new_hash,
                               "change_count": len(changes)}
        return Response({"result": "success", "dry_run": False, "applied": True, "path": path,
                         "old_sha256": current_hash, "new_sha256": new_hash, "diff": diff,
                         "diff_truncated": diff_truncated})


class WorkspaceSearchView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/workspace/search"
    audit_action = "workspace.search"
    audit_resource_type = "service"

    def post(self, request, service_id):
        _require_scope(request.agent, "shell.files.read")
        service = get_service(service_id, request.user, action="can_shell")
        from services.shell import authenticate_session, _resolve_container, _safe_workdir
        from services.api.shell import _assert_managed_target_safe

        session = authenticate_session(service, request.user, _shell_token(request, request.data))
        query = str(request.data.get("query") or "")
        if not query or len(query) > 512 or "\x00" in query:
            raise AgentError("INVALID_REQUEST", "query must be 1 to 512 characters.", status_code=400)
        path = _safe_workdir(request.data.get("path") or ".", session.root_path)
        container = _resolve_container(service)
        safe_path = _assert_managed_target_safe(container, path, session.root_path)
        try:
            limit = max(1, min(int(request.data.get("max_results") or 100), 500))
        except (TypeError, ValueError):
            raise AgentError("INVALID_REQUEST", "max_results must be an integer.", status_code=400)
        argv = ["grep", "-rIn", "--exclude-dir=.git", "--binary-files=without-match", "-m", "1",
                "-E" if request.data.get("regex") is True else "-F", "--", query, safe_path]
        result = container.exec_run(argv, workdir=session.workdir, stdout=True, stderr=True, tty=False)
        output = result.output if isinstance(result.output, (bytes, bytearray)) else b""
        exit_code = int(getattr(result, "exit_code", 1) or 0)
        if exit_code not in (0, 1):
            raise AgentError("WORKSPACE_SEARCH_FAILED", "Workspace search could not complete.",
                             status_code=400, failure_domain="runtime")
        lines = bytes(output).decode("utf-8", "replace").splitlines()
        matches = [{"match": line[:2048]} for line in lines[:limit]]
        return Response({"result": "success", "service_id": str(service.pk), "path": safe_path,
                         "matches": matches, "count": len(matches), "truncated": len(lines) > limit})


class AgentCommandBatchView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/commands/batch"
    audit_action = "commands.batch"
    audit_resource_type = "service"
    audit_mutating = True

    @idempotent
    def post(self, request, service_id):
        _require_scope(request.agent, "shell.execute")
        service = get_service(service_id, request.user, action="can_shell")
        commands = request.data.get("commands")
        if not isinstance(commands, list) or not commands or len(commands) > 10:
            raise AgentError("INVALID_REQUEST", "commands must contain 1 to 10 command entries.", status_code=400)
        try:
            max_output = max(1024, min(int(request.data.get("max_output_bytes") or 65536), 262144))
        except (TypeError, ValueError):
            raise AgentError("INVALID_REQUEST", "max_output_bytes must be an integer.", status_code=400)
        from ..runtime_tools import command_result_from_argv
        results, total_output = [], 0
        for index, item in enumerate(commands):
            if not isinstance(item, dict) or not isinstance(item.get("argv"), list) or not item["argv"]:
                result = {"index": index, "ok": False, "error": "Each command requires a non-empty argv array."}
            else:
                argv = [str(part) for part in item["argv"]]
                if len(argv) > 64 or any(len(part) > 2048 or "\x00" in part for part in argv):
                    result = {"index": index, "ok": False, "error": "Command argument limit exceeded."}
                else:
                    try:
                        safe = redact_shell_result(service, command_result_from_argv(
                            service, request.user, argv, confirm=item.get("confirm") is True))
                        stdout, stderr = str(safe.get("stdout") or ""), str(safe.get("stderr") or "")
                        stdout_raw, stderr_raw = stdout.encode("utf-8"), stderr.encode("utf-8")
                        remaining = max(0, max_output - total_output)
                        stdout_out = stdout_raw[:remaining].decode("utf-8", "ignore")
                        remaining -= len(stdout_out.encode("utf-8"))
                        stderr_out = stderr_raw[:remaining].decode("utf-8", "ignore")
                        used = len(stdout_out.encode("utf-8")) + len(stderr_out.encode("utf-8"))
                        total_output += used
                        command_result = {"index": index, "ok": int(safe.get("exit_code", 1)) == 0,
                                           "argv": argv, "exit_code": safe.get("exit_code"),
                                           "stdout": stdout_out, "stderr": stderr_out,
                                           "stdout_bytes": len(stdout_raw), "stderr_bytes": len(stderr_raw),
                                           "truncated": used < len(stdout_raw) + len(stderr_raw),
                                           "risk": safe.get("risk"), "cwd": safe.get("cwd")}
                        results.append(command_result)
                        if not command_result["ok"] and request.data.get("continue_on_error", True) is False:
                            break
                        continue
                    except AgentError as exc:
                        result = {"index": index, "ok": False, "argv": argv,
                                  "error": {"code": exc.code, "detail": exc.detail,
                                            "failure_domain": exc.failure_domain}}
                    except Exception:
                        result = {"index": index, "ok": False, "argv": argv,
                                  "error": {"code": "COMMAND_FAILED",
                                            "detail": "Command execution failed; inspect the service audit and runtime state."}}
            results.append(result)
            if request.data.get("continue_on_error", True) is False and not result.get("ok"):
                break
        self.audit_metadata = {"command_count": len(commands), "completed_count": len(results),
                               "output_bytes": total_output}
        return Response({"result": "success", "service_id": str(service.pk), "commands": results,
                         "completed": len(results), "failed": sum(not row.get("ok") for row in results),
                         "output_bytes": total_output,
                         "output_truncated": any(row.get("truncated") for row in results)})


def _mcp_tool_definitions(request, service):
    from ..runtime_tools import tools_for_service, serialize_tool

    scopes = set(request.agent.scopes or [])
    try:
        from ..application import ensure_service_access
        ensure_service_access(service, request.user, action="can_shell")
        can_shell = True
    except AgentError:
        can_shell = False
    tools = []
    if "services.read" in scopes:
        tools.append({"name": "service.inspect", "title": "Inspect service",
                      "description": "Return authorized service metadata.",
                      "inputSchema": {"type": "object", "properties": {}},
                      "_meta": {"requiredScopes": ["services.read"]}})
    if can_shell and "shell.read" in scopes and "shell.execute" in scopes:
        tools.extend([
            {"name": "shell.session.create", "title": "Create restricted shell session",
             "description": "Create a temporary restricted shell session and return its short-lived file/PTY token.",
             "inputSchema": {"type": "object", "properties": {
               "mode": {"type": "string", "enum": ["restricted", "developer"] if "shell.developer" in scopes else ["restricted"], "default": "restricted"},
               "workdir": {"type": "string"}}},
             "_meta": {"requiredScopes": ["shell.read", "shell.execute"]}},
            {"name": "shell.session.close", "title": "Close shell session",
             "description": "Close a previously created shell session using its temporary token.",
             "inputSchema": {"type": "object", "required": ["session_id", "shell_token"],
               "properties": {"session_id": {"type": "string"}, "shell_token": {"type": "string"}}},
             "_meta": {"requiredScopes": ["shell.execute"]}},
        ])
    if can_shell and "shell.files.read" in scopes:
        tools.extend([
            {"name": "workspace.tree", "title": "List workspace files",
             "description": "List files and directories inside the restricted service workspace.",
             "inputSchema": {"type": "object", "properties": {"path": {"type": "string"},
               "depth": {"type": "integer", "minimum": 1, "maximum": 8},
               "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
               "offset": {"type": "integer", "minimum": 0},
               "shell_token": {"type": "string"}}},
             "_meta": {"requiredScopes": ["shell.files.read"]}},
            {"name": "workspace.read_many", "title": "Read multiple files",
             "description": "Read up to 30 workspace files in a single tool call.",
             "inputSchema": {"type": "object", "required": ["paths"], "properties": {
               "paths": {"type": "array", "items": {"type": "string"}, "maxItems": 30},
               "max_total_bytes": {"type": "integer", "minimum": 1024, "maximum": 2097152},
               "start_line": {"type": "integer", "minimum": 1},
               "end_line": {"type": "integer", "minimum": 1}, "shell_token": {"type": "string"}}},
             "_meta": {"requiredScopes": ["shell.files.read"]}},
            {"name": "workspace.search", "title": "Search workspace",
             "description": "Search text inside workspace files without downloading the project.",
             "inputSchema": {"type": "object", "required": ["query"], "properties": {
               "query": {"type": "string", "maxLength": 512}, "path": {"type": "string"},
               "regex": {"type": "boolean"}, "max_results": {"type": "integer", "maximum": 500},
               "shell_token": {"type": "string"}}},
             "_meta": {"requiredScopes": ["shell.files.read"]}},
        ])
    if can_shell and "shell.files.write" in scopes:
        tools.extend([
            {"name": "workspace.write_many", "title": "Write multiple files",
             "description": "Write up to 20 files with optional SHA256 preconditions.",
             "inputSchema": {"type": "object", "required": ["files"], "properties": {
               "files": {"type": "array", "maxItems": 20, "items": {"type": "object",
                 "required": ["path", "content"], "properties": {"path": {"type": "string"},
                 "content": {"type": "string"}, "expected_sha256": {"type": "string"}}}},
               "shell_token": {"type": "string"}}},
             "_meta": {"requiredScopes": ["shell.files.write"]}},
            {"name": "workspace.patch", "title": "Patch a file",
             "description": "Apply exact-context replacements after verifying SHA256. Dry-run is the default.",
             "inputSchema": {"type": "object", "required": ["path", "expected_sha256", "changes"],
               "properties": {"path": {"type": "string"}, "expected_sha256": {"type": "string"},
                 "changes": {"type": "array", "maxItems": 50, "items": {"type": "object", "required": ["find", "replace"],
                   "properties": {"find": {"type": "string"}, "replace": {"type": "string"},
                                  "expected_count": {"type": "integer", "default": 1}}}},
                 "dry_run": {"type": "boolean", "default": True}, "apply": {"type": "boolean", "default": False},
                 "shell_token": {"type": "string"}}},
             "_meta": {"requiredScopes": ["shell.files.write"]}},
        ])
    if can_shell and "shell.execute" in scopes:
        tools.append({"name": "command.batch", "title": "Run command batch",
                      "description": "Run up to 10 validated argv commands in one API call.",
                      "inputSchema": {"type": "object", "required": ["commands"], "properties": {
                        "commands": {"type": "array", "maxItems": 10, "items": {"type": "object",
                          "required": ["argv"], "properties": {"argv": {"type": "array", "maxItems": 64, "items": {"type": "string", "maxLength": 2048}},
                                                                "confirm": {"type": "boolean"}}}},
                        "continue_on_error": {"type": "boolean", "default": True},
                        "max_output_bytes": {"type": "integer", "default": 65536}}},
                      "_meta": {"requiredScopes": ["shell.execute"]}})
    for tool in (tools_for_service(request.agent, service) if can_shell else []):
        item = serialize_tool(tool)
        tools.append({"name": item["name"], "title": item["title"], "description": item["summary"],
                      "inputSchema": item["input_schema"],
                      "_meta": {"requiredScopes": item["required_scopes"], "platforms": item["platforms"],
                                "mutating": item["mutating"]}})
    return tools


def _invoke_agent_view(view_class, method, request, *args):
    """Invoke a nested Agent view while preserving its audit/finalization hooks."""
    import time

    view = view_class()
    view._started_at = time.monotonic()
    response = getattr(view, method)(request, *args)
    return view.finalize_response(request, response)


def _mcp_call_tool(request, service_id, name, arguments):
    req = RequestProxy(request, data=arguments)
    # Distinguish idempotency fingerprints for different tools invoked through
    # the same service-scoped MCP URL.
    req.META = {
        **request.META,
        "QUERY_STRING": (str(request.META.get("QUERY_STRING") or "") + "&mcp_tool=" + str(name)),
    }
    if name == "service.inspect":
        _require_scope(request.agent, "services.read")
        return service_payload(get_service(service_id, request.user, action="can_view"))
    if name == "shell.session.create":
        _require_scope(request.agent, "shell.read")
        _require_scope(request.agent, "shell.execute")
        from .shell import ShellSessionView
        response = _invoke_agent_view(ShellSessionView, "post", req, service_id)
        return getattr(response, "data", {})
    if name == "shell.session.close":
        _require_scope(request.agent, "shell.execute")
        from .shell import ShellCloseView
        close_arguments = dict(arguments)
        close_arguments["token"] = arguments.get("shell_token") or arguments.get("token")
        close_request = RequestProxy(request, data=close_arguments)
        response = _invoke_agent_view(ShellCloseView, "post", close_request, service_id, arguments.get("session_id"))
        return getattr(response, "data", {})
    routes = {
        "workspace.tree": (WorkspaceTreeView, "get", "shell.files.read"),
        "workspace.read_many": (WorkspaceReadManyView, "post", "shell.files.read"),
        "workspace.search": (WorkspaceSearchView, "post", "shell.files.read"),
        "workspace.write_many": (WorkspaceWriteManyView, "post", "shell.files.write"),
        "workspace.patch": (WorkspacePatchView, "post", "shell.files.write"),
        "command.batch": (AgentCommandBatchView, "post", "shell.execute"),
    }
    if name in routes:
        view_class, method, scope = routes[name]
        _require_scope(request.agent, scope)
        response = _invoke_agent_view(view_class, method, req, service_id)
        return getattr(response, "data", {})
    from .runtime_tools import RuntimeToolExecuteView
    response = _invoke_agent_view(RuntimeToolExecuteView, "post", req, service_id, name)
    return getattr(response, "data", {})


def _rpc_error(request_id, code, message, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _valid_mcp_origin(request):
    origin = request.headers.get("Origin")
    if not origin:
        return True
    try:
        parsed = urlsplit(origin)
        host = (parsed.hostname or "").lower()
        current = (urlsplit("//" + request.get_host()).hostname or "").lower()
        allowed = {str(value).lower() for value in getattr(settings, "ALLOWED_HOSTS", [])
                   if value and value != "*"}
        trusted = {((urlsplit(str(value)).hostname or "").lower())
                   for value in getattr(settings, "CSRF_TRUSTED_ORIGINS", [])}
        return parsed.scheme in {"http", "https"} and bool(host) and (
            host == current or host in allowed or host in trusted)
    except Exception:
        return False


class AgentMCPView(AgentSecuredAPIView):
    """Stateless MCP Streamable HTTP endpoint, one endpoint per Service."""

    agent_contract_path = "/agent/v1/services/{service_id}/mcp"
    audit_action = "agent.mcp.request"
    audit_resource_type = "service"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["MCP-Protocol-Version"] = request.headers.get("MCP-Protocol-Version") or MCP_PROTOCOL_VERSION
        return response

    def _success_result(self, protocol, payload):
        if protocol == MCP_PROTOCOL_VERSION:
            return {
                **payload,
                "resultType": "complete",
                "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "PassDeployer", "version": "1"}},
            }
        return payload

    def post(self, request, service_id):
        if not _valid_mcp_origin(request):
            return Response(_rpc_error(None, -32600, "Invalid Origin header."), status=403)
        service = get_service(service_id, request.user, action="can_view")
        accept = request.headers.get("Accept", "")
        if "application/json" not in accept or "text/event-stream" not in accept:
            return Response(_rpc_error(None, -32600, "Accept must include application/json and text/event-stream."), status=406)
        if request.content_type != "application/json":
            return Response(_rpc_error(None, -32600, "Content-Type must be application/json."), status=415)
        protocol = request.headers.get("MCP-Protocol-Version", "")
        message = request.data if isinstance(request.data, dict) else None
        if not message or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return Response(_rpc_error(None, -32600, "Invalid JSON-RPC request."), status=400)
        method, params = message["method"], message.get("params") or {}
        request_id = message.get("id")
        mcp_tool_name = str(params.get("name") or "") if isinstance(params, dict) else ""
        self.audit_metadata = {"mcp_method": method, "mcp_tool": mcp_tool_name,
                               "mcp_protocol": protocol}
        if method == "tools/call":
            self.audit_action = f"agent.mcp.tool.{mcp_tool_name[:80] or 'unknown'}"
            self.audit_resource_type = "service"
            read_only_tools = {
                "service.inspect", "workspace.tree", "workspace.read_many",
                "workspace.search", "workspace.inspect", "runtime.detect",
                "php.lint", "database.health", "wordpress.status", "wordpress.inspect",
            }
            self.audit_mutating = mcp_tool_name not in read_only_tools
            if mcp_tool_name == "workspace.patch":
                args = params.get("arguments") or {}
                self.audit_mutating = args.get("dry_run", True) is False and args.get("apply") is True
        if method.startswith("notifications/") and "id" not in message:
            return Response(status=202)
        if protocol not in MCP_SUPPORTED_VERSIONS:
            return Response(_rpc_error(None, -32022, "Unsupported MCP protocol version.",
                              {"kind": "UnsupportedProtocolVersionError", "supported": list(MCP_SUPPORTED_VERSIONS)}), status=400)
        self.audit_metadata = {"mcp_method": method,
                               "mcp_tool": str(params.get("name") or "") if isinstance(params, dict) else ""}
        if not isinstance(params, dict):
            return Response(_rpc_error(request_id, -32602, "params must be an object."), status=400)
        # Notifications have no request ID. This transport accepts them with
        # the required empty 202 response; the 2026 revision does not define
        # request metadata headers for client-sent notifications.
        if (not isinstance(request_id, (str, int)) or isinstance(request_id, bool)):
            return Response(_rpc_error(None, -32600, "JSON-RPC requests require a string or integer id."), status=400)
        if protocol == MCP_PROTOCOL_VERSION:
            meta = params.get("_meta")
            if not isinstance(meta, dict):
                return Response(_rpc_error(request_id, -32602, "params._meta is required."), status=400)
            if not isinstance(meta.get("io.modelcontextprotocol/clientCapabilities"), dict):
                return Response(_rpc_error(request_id, -32602, "clientCapabilities must be an object in params._meta."), status=400)
            if meta.get("io.modelcontextprotocol/protocolVersion") != protocol:
                return Response(_rpc_error(request_id, -32020, "MCP protocol version header does not match params._meta.",
                                  {"kind": "HeaderMismatch"}), status=400)
            if request.headers.get("Mcp-Method") != method:
                return Response(_rpc_error(request_id, -32020, "Mcp-Method must match the JSON-RPC method.",
                                  {"kind": "HeaderMismatch"}), status=400)
            if method == "tools/call" and (
                not isinstance(params.get("name"), str)
                or request.headers.get("Mcp-Name") != str(params.get("name"))
            ):
                return Response(_rpc_error(request_id, -32020, "Mcp-Name must match params.name.",
                                  {"kind": "HeaderMismatch"}), status=400)
        if method == "initialize":
            if protocol == MCP_PROTOCOL_VERSION:
                return Response(_rpc_error(request_id, -32601, "initialize is not used by the stateless 2026-07-28 transport."), status=404)
            return Response({"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": MCP_LEGACY_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "PassDeployer", "version": "1"},
                "instructions": "Use tools/list to discover per-service tools; scopes and service permissions apply."}})
        if method == "ping":
            result = self._success_result(protocol, {})
            return Response({"jsonrpc": "2.0", "id": request_id, "result": result})
        if method == "tools/list":
            result = self._success_result(protocol, {"tools": _mcp_tool_definitions(request, service),
                                                       "cacheScope": "private", "ttlMs": 15000})
            return Response({"jsonrpc": "2.0", "id": request_id, "result": result})
        if method == "tools/call":
            name = str(params.get("name") or "")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                return Response(_rpc_error(request_id, -32602, "Tool arguments must be an object."), status=400)
            try:
                result = _mcp_call_tool(request, service_id, name, arguments)
                text = json.dumps(result, ensure_ascii=False, default=str)
                body = self._success_result(protocol, {
                    "content": [{"type": "text", "text": text}],
                    "structuredContent": result, "isError": False})
                return Response({"jsonrpc": "2.0", "id": request_id, "result": body})
            except AgentError as exc:
                self.audit_mutating = False
                detail = {"code": exc.code, "detail": exc.detail,
                          "failure_domain": exc.failure_domain, **(exc.extra or {})}
                body = self._success_result(protocol, {
                    "content": [{"type": "text", "text": json.dumps(detail, ensure_ascii=False)}],
                    "structuredContent": detail, "isError": True})
                return Response({"jsonrpc": "2.0", "id": request_id, "result": body})
            except Exception:
                self.audit_mutating = False
                detail = {"code": "TOOL_EXECUTION_FAILED",
                          "detail": "Tool execution failed; inspect the request ID and service audit event."}
                body = self._success_result(protocol, {
                    "content": [{"type": "text", "text": json.dumps(detail, ensure_ascii=False)}],
                    "structuredContent": detail, "isError": True})
                return Response({"jsonrpc": "2.0", "id": request_id, "result": body})
        return Response(_rpc_error(request_id, -32601, f"Method not found: {method}"), status=404)
