from __future__ import annotations

from rest_framework.response import Response
from .base import AgentSecuredAPIView, idempotent
from ..application import call_api_view_handler, ensure_service_access, get_service, redact_shell_result
from ..errors import AgentError


class ShellInfoView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/shell"

    def get(self,request,service_id):
        service=get_service(service_id,request.user,action="can_view")
        from services.shell import (
            command_catalog,
            _platform_for_service,
            can_use_advanced_shell,
            shell_protocol_metadata,
            shell_workspace_metadata,
        )
        allowed = ensure_service_access(service, request.user, action="can_shell")
        platform = _platform_for_service(service)
        advanced = bool(can_use_advanced_shell(service, request.user))
        protocol = shell_protocol_metadata(service.pk)
        protocol["interactive_pty"]["requires_advanced_user_access_for_repl"] = advanced
        return Response({
            "result": "success",
            "service_id": str(service.pk),
            "enabled": bool(allowed is not False and "shell.execute" in set(request.agent.scopes or [])),
            "platform": platform,
            "advanced_interactive": advanced,
            "commands": command_catalog(platform, service),
            "transport": protocol,
            "policy": protocol["policy"],
            "workspace": shell_workspace_metadata(service),
        })

class ShellSessionView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/shell/sessions"

    def post(self,request,service_id):
        service=get_service(service_id,request.user,action="can_shell")
        from services.shell import create_session, can_use_advanced_shell
        mode=str(request.data.get("mode") or "restricted").strip().lower()
        if mode == "developer":
            if "shell.developer" not in set(request.agent.scopes or []):
                raise AgentError("INSUFFICIENT_SCOPE","Developer shell requires the shell.developer Agent scope.",status_code=403,failure_domain="authorization")
            if not can_use_advanced_shell(service, request.user):
                raise AgentError("AUTHORIZATION_FAILED","Developer shell requires advanced shell service permission.",status_code=403,failure_domain="authorization")
        session,token=create_session(service,request.user,request.data.get("workdir"),mode=mode)
        self.audit_metadata={"session_id":str(session.pk),"service_id":str(service.pk)}
        from services.shell import shell_workspace_metadata
        return Response({"result":"success","session_id":str(session.pk),"token":token,"token_type":"Shell","platform":session.platform,"cwd":session.workdir,"mode":session.mode,"expires_at":session.expires_at,"workspace":shell_workspace_metadata(service)},status=201)

class ShellCommandView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/shell/sessions/{session_id}/commands"

    def post(self,request,service_id,session_id):
        service=get_service(service_id,request.user,action="can_shell")
        token=request.headers.get("X-Shell-Token") or request.data.get("token")
        if not token:raise AgentError("SHELL_TOKEN_REQUIRED","X-Shell-Token is required.",status_code=401,failure_domain="authentication")
        from services.shell import authenticate_session,execute_command
        session=authenticate_session(service,request.user,token)
        if str(session.pk)!=str(session_id):raise AgentError("SHELL_SESSION_MISMATCH","Shell session does not match this service.",status_code=403,failure_domain="authorization")
        command=str(request.data.get("command") or "")
        if not command:raise AgentError("INVALID_REQUEST","command is required.",status_code=400)
        result=execute_command(session,command,confirm=bool(request.data.get("confirm",False)),dry_run=bool(request.data.get("dry_run",False)))
        safe=redact_shell_result(service,result)
        try:
            output_limit = max(1024, min(int(request.data.get("max_output_bytes") or 65536), 262144))
        except (TypeError, ValueError):
            raise AgentError("INVALID_REQUEST", "max_output_bytes must be an integer.", status_code=400)
        output_mode = str(request.data.get("output_mode") or "full").strip().lower()
        if output_mode not in {"full", "summary"}:
            raise AgentError("INVALID_REQUEST", "output_mode must be full or summary.", status_code=400)
        stdout_raw = str(safe.get("stdout") or "").encode("utf-8")
        stderr_raw = str(safe.get("stderr") or "").encode("utf-8")
        if output_mode == "summary":
            stdout_text = stdout_raw[:512].decode("utf-8", "ignore")
            stderr_text = stderr_raw[:512].decode("utf-8", "ignore")
        else:
            stdout_cap = min(len(stdout_raw), (output_limit * 3) // 4)
            stderr_cap = min(len(stderr_raw), output_limit - stdout_cap)
            spare = output_limit - stdout_cap - stderr_cap
            if spare:
                extra_stdout = min(spare, len(stdout_raw) - stdout_cap)
                stdout_cap += extra_stdout
                spare -= extra_stdout
            if spare:
                stderr_cap += min(spare, len(stderr_raw) - stderr_cap)
            stdout_text = stdout_raw[:stdout_cap].decode("utf-8", "ignore")
            stderr_text = stderr_raw[:stderr_cap].decode("utf-8", "ignore")
        output_truncated = (
            len(stdout_text.encode("utf-8")) < len(stdout_raw)
            or len(stderr_text.encode("utf-8")) < len(stderr_raw)
        )
        self.audit_metadata={"session_id":str(session.pk),"command_length":len(command),"exit_code":safe.get("exit_code"),"risk":safe.get("risk"),
                             "output_bytes":len(stdout_text.encode("utf-8")) + len(stderr_text.encode("utf-8")),
                             "output_truncated":output_truncated}
        payload = {
            "result": "success",
            "command": safe.get("command") or command,
            "exit_code": safe.get("exit_code"),
            "stdout": stdout_text,
            "stderr": stderr_text,
            "stdout_bytes": len(stdout_raw),
            "stderr_bytes": len(stderr_raw),
            "output_bytes": len(stdout_text.encode("utf-8")) + len(stderr_text.encode("utf-8")),
            "output_truncated": output_truncated,
            "output_mode": output_mode,
            "duration_ms": safe.get("duration_ms"),
            "cwd": safe.get("cwd") or session.workdir,
            "session_id": str(session.pk),
        }
        for key in ("dry_run", "risk", "requires_confirmation", "plan"):
            if key in safe:
                payload[key] = safe[key]
        return Response(payload)

class ShellCloseView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/shell/sessions/{session_id}/close"

    @idempotent
    def post(self,request,service_id,session_id):
        service=get_service(service_id,request.user,action="can_shell")
        token=request.headers.get("X-Shell-Token") or request.data.get("token")
        if not token:raise AgentError("SHELL_TOKEN_REQUIRED","X-Shell-Token is required.",status_code=401,failure_domain="authentication")
        from services.shell import authenticate_session,close_session
        session=authenticate_session(service,request.user,token)
        if str(session.pk)!=str(session_id):raise AgentError("SHELL_SESSION_MISMATCH","Shell session does not match this service.",status_code=403,failure_domain="authorization")
        close_session(session); return Response({"result":"success"})

class ShellReplaceView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/shell/replace"

    def post(self,request,service_id):
        service=get_service(service_id,request.user,action="can_shell")
        ensure_service_access(service,request.user,action="can_shell_replace")
        if request.data.get("confirm") is not True:raise AgentError("CONFIRMATION_REQUIRED","confirm=true is required to replace the active shell session.",status_code=409,failure_domain="authorization")
        from services.shell import terminate_active_session,create_session
        mode=str(request.data.get("mode") or "restricted").strip().lower()
        if mode == "developer":
            if "shell.developer" not in set(request.agent.scopes or []):
                raise AgentError("INSUFFICIENT_SCOPE","Developer shell requires the shell.developer Agent scope.",status_code=403,failure_domain="authorization")
            from services.shell import can_use_advanced_shell
            if not can_use_advanced_shell(service, request.user):
                raise AgentError("AUTHORIZATION_FAILED","Developer shell requires advanced shell service permission.",status_code=403,failure_domain="authorization")
        old=terminate_active_session(service,actor=request.user); session,token=create_session(service,request.user,request.data.get("workdir"),mode=mode)
        return Response({"result":"success","replaced":bool(old),"previous_session_id":str(old.pk) if old else None,"session_id":str(session.pk),"token":token,"expires_at":session.expires_at,"cwd":session.workdir,"mode":session.mode},status=201)

class ShellFileView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/shell/files"

    def post(self,request,service_id):
        action=str(request.data.get("action") or "read").lower()
        scope="shell.files.write" if action in {"write","delete","rename","create","create_folder","upload"} else "shell.files.read"
        if scope not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE",f"Missing {scope} scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user,action="can_shell")
        from services.api.shell import shell_file_apiview
        self.audit_action=f"shell.file.{action}"; self.audit_mutating=scope.endswith("write")
        return call_api_view_handler(shell_file_apiview,request,"post",service_id)

