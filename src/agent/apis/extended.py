"""Higher-level discovery and sensitive operational APIs for Agent clients."""
from __future__ import annotations

from django.utils import timezone
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .base import AgentSecuredAPIView
from ..application import call_api_view_handler, get_service
from ..errors import AgentError
from ..security import sanitize_metadata


class DeploymentHelpView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/deployments/help"
    audit_action = "deployments.help.read"
    audit_resource_type = "deployment"

    def get(self, request):
        from deployments.common.config import TENANT_BLOCKED_KEYS, TENANT_CONFIG_KEYS
        from deployments.core.platform_bridge import _ensure_plugins_loaded
        from deployments.core.platforms.registry import PlatformRegistry
        from core.global_settings.config import PLATFORM_CHOICES

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


class DatabaseCredentialsView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/database-credentials"
    audit_action = "service_database_credentials.read"
    audit_resource_type = "service"
    suppress_error_fields = True
    idempotency_store_response = False

    def get(self, request, service_id):
        from services.models import ServiceDatabaseBinding

        service = get_service(service_id, request.user, action="can_view", owner_only=True)
        reveal = str(request.query_params.get("reveal") or "").strip().lower() in {"1", "true", "yes", "on"}
        bindings = (
            ServiceDatabaseBinding.objects
            .filter(service=service)
            .select_related("database", "database__credential")
            .order_by("alias")
        )
        rows = []
        for binding in bindings:
            database = binding.database
            credential = getattr(database, "credential", None)
            password = credential.get_password() if reveal and credential else None
            rows.append({
                "id": str(binding.pk),
                "alias": binding.alias,
                "env_prefix": binding.env_prefix,
                "access_mode": binding.access_mode,
                "database": {
                    "id": str(database.pk),
                    "name": database.name,
                    "engine": database.engine,
                    "host": database.host,
                    "port": database.port,
                    "database_name": database.database_name,
                    "status": database.status,
                    "provider_service": str(database.provider_service_id) if database.provider_service_id else None,
                },
                "credentials": {
                    "username": getattr(credential, "username", "") if credential else "",
                    "password": password,
                    "password_available": bool(credential and getattr(credential, "password_ciphertext", "")),
                    "revealed": reveal,
                },
            })
        response = Response({
            "result": "success",
            "service_id": str(service.pk),
            "owner_only": True,
            "reveal_requires_scope": "service_database_credentials.read",
            "results": rows,
        })
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response
