from __future__ import annotations

from django.http import HttpResponse, JsonResponse
from rest_framework.response import Response
from .base import AgentPublicAPIView, AgentSecuredAPIView
from ..application import create_enrollment, issue_access_credential
from ..contracts import contracts_for_agent
from ..scopes import SERVICE_SCOPES, HIGH_RISK_SCOPES, scope_categories


class AgentRootView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/"
    audit_action = "agent.identity.read"
    def get(self, request):
        a = request.agent
        return Response({
            "result": "success", "api_version": "v1",
            "agent": {"id": str(a.pk), "name": a.name, "description": a.description, "status": a.status},
            "user": {"id": str(a.user_id), "username": a.user.username},
            "scopes": sorted(a.scopes or []),
            "links": {"capabilities": "/agent/v1/capabilities", "openapi": "/agent/v1/openapi.json", "agent_md": "/agent/v1/agent.md"},
        })

class AgentExchangeView(AgentPublicAPIView):
    agent_contract_path = "/agent/v1/auth/exchange"
    audit_action = "credential.exchange"
    def post(self, request):
        from ..application import exchange_enrollment
        agent, credential, access = exchange_enrollment(
            request.data.get("enrollment_token"),
            metadata={"client": str(request.data.get("client") or "")[:100]},
        )
        request.agent = agent
        request.agent_credential = credential
        self.audit_metadata = {"credential_prefix": credential.token_prefix}
        response = Response({
            "result": "success", "token": access, "token_type": "Bearer",
            "expires_at": credential.expires_at,
            "agent": {"id": str(agent.pk), "name": agent.name},
            "scopes": sorted(agent.scopes or []),
        }, status=201)
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response

class AgentMeView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/auth/me"
    audit_action = "agent.identity.me"
    def get(self, request):
        c = request.agent_credential
        return Response({
            "result": "success", "agent_id": str(request.agent.pk), "name": request.agent.name,
            "user": {"id": str(request.user.pk), "username": request.user.username},
            "scopes": sorted(request.agent.scopes or []),
            "credential": {"id": str(c.pk), "prefix": c.token_prefix, "expires_at": c.expires_at, "last_used_at": c.last_used_at},
        })

class AgentCapabilitiesView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/capabilities"
    audit_action = "agent.capabilities.read"
    def get(self, request):
        s = set(request.agent.scopes or [])
        return Response({
            "api_version": "v1", "agent_id": str(request.agent.pk), "scopes": sorted(s),
            "scope_categories": scope_categories(s),
            "capabilities": {
                "services": {
                    **{scope.split(".",1)[1]: scope in s for scope in SERVICE_SCOPES},
                    "metrics": "services.read" in s,
                },
                "plans": {"read":"plans.read" in s,"apply":"plans.apply" in s and "services.create" in s,"manage":"plans.manage" in s},
                "deployments": {
                    **{x.split(".",1)[1]: x in s for x in (
                        "deployments.read","deployments.create","deployments.upload","deployments.start","deployments.cancel",
                        "deployments.redeploy","deployments.rebuild","deployments.rollback","deployments.delete")},
                    "help": "deployments.read" in s,
                    "inspect": "deployments.upload" in s,
                },
                "logs": {"deployment_read":"deployments.logs.read" in s,"deployment_export":"deployments.logs.export" in s,"runtime_read":"service_logs.read" in s,"runtime_export":"service_logs.export" in s},
                "shell": {"read":"shell.read" in s,"execute":"shell.execute" in s,"replace":"shell.replace" in s,"files_read":"shell.files.read" in s,"files_write":"shell.files.write" in s},
                "database": {"credentials_read": "service_database_credentials.read" in s},
                "agent": {"manifest_generate":"agent.manifest.generate" in s},
            },
            "deployment_inputs": {"archive_zip": True, "database_native": True, "git": False, "existing_image": False},
            "logs": {
                "deployment": {"model":"DeployLog","database_alias":"deployment_logs"},
                "runtime": {"models":["ServiceLogStream","ServiceLogEntry"],"database_alias":"deployment_logs"},
            },
            "pagination": {"default_page_size": 25, "max_page_size": 100},
            "idempotency": {"header":"Idempotency-Key","ttl_hours":24,"important_mutations":True},
            "operations": [
                {
                    "method": item.method,
                    "path": item.path,
                    "required_scopes": list(item.scopes),
                    "required_any_scopes": list(item.any_scopes),
                    "mutating": item.mutating,
                    "idempotent": item.idempotent,
                    "throttle_scope": item.throttle_scope,
                }
                for item in contracts_for_agent(request.agent)
            ],
            "high_risk_scopes": sorted(HIGH_RISK_SCOPES & s),
            "unsupported": ["Git deployment input", "existing-image deployment input", "host shell", "raw Docker API"],
            "confirmation": {"shell_destructive_commands": True, "deployment_rebuild": "deployments.rebuild" in s, "deployment_rollback": "deployments.rollback" in s},
        })

class AgentManifestView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/agent.md"


    audit_action = "agent.manifest.generate"
    def get(self, request):
        from ..manifest import render_agent_manifest
        enrollment, row = create_enrollment(request.agent, request=request)
        credential, access = issue_access_credential(
            request.agent,
            metadata={"issued_via": "agent_manifest"},
        )
        self.audit_metadata = {
            "enrollment_prefix": row.token_prefix,
            "enrollment_expires_at": row.expires_at.isoformat(),
            "credential_prefix": credential.token_prefix,
            "credential_expires_at": credential.expires_at.isoformat(),
        }
        response = HttpResponse(
            render_agent_manifest(
                request.agent,
                enrollment,
                access_token=access,
                request=request,
            ),
            content_type="text/markdown; charset=utf-8",
        )
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response

class AgentOpenAPIView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/openapi.json"
    audit_action = "agent.openapi.read"
    def get(self, request):
        from ..openapi import build_openapi
        return JsonResponse(build_openapi(request.agent, request=request), json_dumps_params={"indent":2})

