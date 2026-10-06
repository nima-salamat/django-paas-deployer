from __future__ import annotations

from rest_framework.response import Response

from .base import AgentSecuredAPIView, idempotent
from ..application import get_service
from ..errors import AgentError
from ..runtime_tools import (
    serialize_tool,
    tool_for_service,
    tools_for_service,
)


class RuntimeToolIndexView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/tools"

    def get(self, request, service_id):
        service = get_service(service_id, request.user, action="can_shell")
        tools = tools_for_service(request.agent, service)
        return Response({
            "result": "success",
            "service_id": str(service.pk),
            "platform": __import__("services.shell", fromlist=["_platform_for_service"])._platform_for_service(service),
            "tools": [serialize_tool(tool) for tool in tools],
        })


class RuntimeToolExecuteView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/tools/{tool_name}"

    @idempotent
    def post(self, request, service_id, tool_name):
        service = get_service(service_id, request.user, action="can_view")
        from services.shell import _platform_for_service
        platform = _platform_for_service(service)
        tool = tool_for_service(request.agent, service, tool_name)
        if tool is None:
            from ..runtime_tools import TOOLS
            known = next((item for item in TOOLS if item.name == str(tool_name)), None)
            if known is None:
                raise AgentError(
                    "TOOL_NOT_FOUND",
                    "The requested runtime tool does not exist.",
                    status_code=404,
                    failure_domain="resource",
                )
            if not known.applies_to(platform):
                raise AgentError(
                    "TOOL_NOT_APPLICABLE",
                    f"Tool '{known.name}' is not available for platform '{platform}'.",
                    status_code=422,
                    failure_domain="request",
                    extra={"platform": platform, "tool": known.name, "applicable_platforms": list(known.platforms)},
                )
            missing = [scope for scope in known.scopes if scope not in set(request.agent.scopes or [])]
            raise AgentError(
                "INSUFFICIENT_SCOPE",
                "The Agent does not have the scope required by this runtime tool.",
                status_code=403,
                failure_domain="authorization",
                extra={"missing_scopes": missing},
            )
        payload = dict(request.data) if isinstance(request.data, dict) else {}
        self.audit_action = f"runtime_tool.{tool.name}"
        self.audit_resource_type = "service"
        self.audit_mutating = bool(tool.mutating)
        self.audit_metadata = {
            "tool": tool.name,
            "platform": platform,
            "argument_keys": sorted(
                str(key) for key in payload.keys()
                if str(key) not in {"password", "secret", "token", "credential"}
            ),
            "argument_count": len(payload),
            "has_confirmation": bool(payload.get("confirm")),
        }
        result = tool.handler(service, request.user, payload) if tool.handler else {}
        output = result if isinstance(result, dict) else {"value": result}
        risk = str(output.get("risk") or "").upper()
        self.audit_mutating = bool(tool.mutating and risk not in {"READ_ONLY", ""})
        return Response({
            "result": "success",
            "service_id": str(service.pk),
            "tool": tool.name,
            "platform": platform,
            "output": output,
        })
