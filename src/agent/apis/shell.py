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
            "commands": command_catalog(platform),
            "transport": protocol,
            "policy": protocol["policy"],
            "workspace": shell_workspace_metadata(service),
        })

class ShellSessionView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/shell/sessions"

    def post(self,request,service_id):
        service=get_service(service_id,request.user,action="can_shell")
        from services.shell import create_session
        session,token=create_session(service,request.user,request.data.get("workdir"))
        self.audit_metadata={"session_id":str(session.pk),"service_id":str(service.pk)}
        return Response({"result":"success","session_id":str(session.pk),"token":token,"token_type":"Shell","platform":session.platform,"cwd":session.workdir,"expires_at":session.expires_at},status=201)

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
        self.audit_metadata={"session_id":str(session.pk),"command_length":len(command),"exit_code":safe.get("exit_code"),"risk":safe.get("risk")}
        payload = {
            "result": "success",
            "command": safe.get("command") or command,
            "exit_code": safe.get("exit_code"),
            "stdout": safe.get("stdout"),
            "stderr": safe.get("stderr"),
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
        old=terminate_active_session(service,actor=request.user); session,token=create_session(service,request.user,request.data.get("workdir"))
        return Response({"result":"success","replaced":bool(old),"previous_session_id":str(old.pk) if old else None,"session_id":str(session.pk),"token":token,"expires_at":session.expires_at,"cwd":session.workdir},status=201)

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

