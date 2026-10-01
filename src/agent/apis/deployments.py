from __future__ import annotations

from rest_framework.response import Response
from django.http import HttpResponse
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from .base import AgentSecuredAPIView, AgentPage, idempotent
from ..security import sanitize_metadata
from .helpers import _DeploymentSerializer
from ..application import (
    call_api_view_handler, call_viewset_action, deployment_payload, deployment_queryset,
    get_deployment, get_service, upload_deployment_zip,
)
from ..errors import AgentError


class DeploymentListCreateView(AgentPage):
    agent_contract_path = "/agent/v1/deployments"

    audit_resource_type="deployment"
    def get(self,request): self.audit_action="deployments.list"; return self.paginate(request,deployment_queryset(request.user),_DeploymentSerializer)
    @idempotent
    def post(self,request):
        from ..application import create_deployment
        d=create_deployment(request,dict(request.data)); self.audit_action="deployments.create"; self.audit_mutating=True
        return Response({"result":"success","deployment":deployment_payload(d)},status=201)

class DeploymentDetailView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/deployments/{deployment_id}"

    audit_resource_type="deployment"
    def get(self,request,deployment_id): return Response({"result":"success","deployment":deployment_payload(get_deployment(deployment_id,request.user))})
    @idempotent
    def delete(self,request,deployment_id):
        from deploy.apis import DeployViewSet
        d=get_deployment(deployment_id,request.user,action="can_deploy_remove")
        response=call_viewset_action(DeployViewSet,"destroy",request,pk=d.pk)
        self.audit_action="deployments.delete"; self.audit_mutating=True; return response

class DeploymentUploadView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/deployments/{deployment_id}/upload"

    @idempotent
    def post(self,request,deployment_id):
        d=upload_deployment_zip(request,deployment_id)
        return Response({"result":"success","deployment":deployment_payload(d)})

class DeploymentActionView(AgentSecuredAPIView):
    def get_agent_contract_path(self, request):
        return f'/agent/v1/deployments/{{deployment_id}}/{self.kwargs.get("action")}'

    @idempotent
    def post(self,request,deployment_id,action):
        response=__import__("agent.application",fromlist=["deployment_action"]).deployment_action(request,deployment_id,action)
        self.audit_action=f"deployments.{action}"; return response

class DeploymentRollbackView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/deployments/{deployment_id}/rollback"

    @idempotent
    def post(self,request,deployment_id):
        d=get_deployment(deployment_id,request.user,action="can_deploy_add")
        if not d.revision_id:raise AgentError("ROLLBACK_UNAVAILABLE","Deployment has no immutable revision.",status_code=409,failure_domain="resource")
        from services.api.configuration import ServiceRevisionRollbackAPIView
        return ServiceRevisionRollbackAPIView().post(__import__("agent.application",fromlist=["RequestProxy"]).RequestProxy(request),d.service_id,d.revision_id)

class DeploymentLogsView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/deployments/{deployment_id}/logs"

    def get(self,request,deployment_id):
        from deploy.apis import deploy_logs_apiview
        d=get_deployment(deployment_id,request.user)
        response=call_api_view_handler(deploy_logs_apiview,request,"get",d.pk)
        if isinstance(getattr(response,"data",None),dict):
            payload=dict(response.data); rows=[]
            for row in payload.get("logs") or []:
                rows.append({"timestamp":row.get("created_at"),"level":row.get("level"),"source":"deployment","stage":row.get("stage"),"event_type":row.get("event_type"),"message":row.get("message"),"deployment_id":str(d.pk),"service_id":str(d.service_id)})
            payload["logs"]=rows; payload["deployment"]=deployment_payload(d); payload["source"]="deployment"; response.data=payload
        return response

class DeploymentLogsExportView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/deployments/{deployment_id}/logs/export"

    def get(self,request,deployment_id):
        from deploy.apis import deploy_logs_export_apiview
        d=get_deployment(deployment_id,request.user)
        return call_api_view_handler(deploy_logs_export_apiview,request,"get",d.pk)



class DeploymentHelpView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/deployments/help"
    audit_action = "deployments.help.read"
    audit_resource_type = "deployment"

    def get(self, request):
        from deployments.common.config import TENANT_BLOCKED_KEYS, TENANT_CONFIG_KEYS
        from deployments.core.platform_bridge import _ensure_plugins_loaded
        from deployments.core.platforms.registry import PlatformRegistry
        from core.global_settings.config import PLATFORM_CHOICES
        from deployments.core.db_deployer import DB_PLATFORMS, MUTABLE_DB_CONFIG_KEYS, validate_db_config

        _ensure_plugins_loaded()
        platform_labels = {str(value): str(label) for value, label in PLATFORM_CHOICES}
        platforms = []
        for plugin_cls in PlatformRegistry.all_plugins():
            platform = str(plugin_cls.name)
            plugin = plugin_cls("")
            schema = {}
            for key, option in plugin.schema().items():
                schema[str(key)] = {
                    "required": bool(option.required),
                    "auto_detect": bool(option.auto_detect),
                    "default": sanitize_metadata(option.default),
                    "description": str(option.description or ""),
                    "tenant_configurable": str(key) in TENANT_CONFIG_KEYS and str(key) not in TENANT_BLOCKED_KEYS,
                }
            platforms.append({
                "name": platform,
                "label": platform_labels.get(platform, platform.replace("_", " ").title()),
                "priority": int(getattr(plugin_cls, "priority", 0)),
                "defaults": sanitize_metadata(plugin.defaults()),
                "schema": schema,
            })

        return Response({
            "result": "success",
            "deployment_inputs": {
                "archive_zip": True,
                "database_native": True,
                "git": False,
                "existing_image": False,
            },
            "database_deployment": {
                "platforms": sorted(DB_PLATFORMS),
                "default_ports": {
                    "mysql": 3306, "mariadb": 3306, "postgresql": 5432,
                    "mongodb": 27017, "redis": 6379, "oracle": 1521,
                },
                "fields": {
                    "root_password": {"type": "secret", "required_for": ["mysql", "mariadb"]},
                    "username": {"type": "string", "required_for": ["mongodb"], "optional_for": ["mysql", "mariadb", "postgresql", "oracle"]},
                    "password": {"type": "secret", "required_for": ["postgresql", "mongodb", "oracle"], "alias_for_root_password_on": ["mysql", "mariadb"]},
                    "database": {"type": "string", "required_for": [], "description": "Optional database name where supported."},
                    "port": {"type": "integer", "minimum": 1, "maximum": 65535, "default_by_platform": {"mysql": 3306, "mariadb": 3306, "postgresql": 5432, "mongodb": 27017, "redis": 6379, "oracle": 1521}},
                },
                "mutable_keys": sorted(MUTABLE_DB_CONFIG_KEYS),
                "validation": "Use the same platform validator used by deployment execution; credentials are never echoed by the help endpoint.",
            },
            "config": {
                "fields": {
                    key: {
                        **dict(spec),
                        "operator_only": key in TENANT_BLOCKED_KEYS,
                        "tenant_configurable": key not in TENANT_BLOCKED_KEYS,
                    }
                    for key, spec in TENANT_CONFIG_KEYS.items()
                },
                "blocked_keys": sorted(TENANT_BLOCKED_KEYS),
                "semantics": {
                    "merge_order": ["platform_default", "auto_detect", "user_config"],
                    "unknown_keys": "warning_and_ignored",
                    "resource_limits": "server_owned_from_service_plan",
                    "worker_count": "server_owned_from_service_plan",
                },
            },
            "platforms": platforms,
            "lifecycle": {
                "service_actions": {
                    "start": "desired_state=running; queues deployment without changing the revision",
                    "stop": "desired_state=stopped; queues runtime stop",
                    "restart": "ordered runtime restart; does not create a new revision",
                    "rebuild": "tears down the current runtime and queues the active revision with force_rebuild",
                },
                "deployment_actions": {
                    "start": "execute selected deployment revision",
                    "redeploy": "repeat deployment execution for the selected deployment",
                    "rebuild": "rebuild runtime/image path using the existing deployment",
                    "cancel": "request cancellation through the deployment state machine",
                    "rollback": "activate an immutable previous revision",
                },
            },
            "runtime_policy": {
                "resource_source": "selected Service Plan",
                "tenant_resource_overrides": False,
                "host_shell": False,
                "raw_docker_api": False,
                "share_permissions": "existing ServiceShare rules remain authoritative",
                "confirmation": ["destructive shell commands", "shell session replacement"],
            },
            "workflow": [
                "GET /agent/v1/plans",
                "POST /agent/v1/services",
                "GET /agent/v1/deployments/help",
                "POST /agent/v1/deployments",
                "POST /agent/v1/deployments/{deployment_id}/upload",
                "POST /agent/v1/deployments/{deployment_id}/start",
                "GET /agent/v1/services/{service_id}/status",
                "GET /agent/v1/services/{service_id}/metrics",
                "GET /agent/v1/services/{service_id}/logs",
            ],
        })

class DeploymentInspectView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/deployments/inspect"
    audit_action = "deployments.inspect"
    audit_resource_type = "deployment"

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        upload = request.FILES.get("file") or request.FILES.get("zip_file")
        if upload is None:
            raise AgentError(
                "INVALID_REQUEST",
                "A ZIP file is required in multipart field 'file'.",
                status_code=400,
                failure_domain="request",
            )
        from deploy.apis import inspect_deploy_zip_apiview
        return call_api_view_handler(inspect_deploy_zip_apiview, request, "post")
