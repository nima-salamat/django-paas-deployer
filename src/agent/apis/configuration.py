from __future__ import annotations

from rest_framework.response import Response
from django.http import HttpResponse
from .base import AgentSecuredAPIView, idempotent
from ..application import call_api_view_handler, get_service, ensure_service_access
from ..errors import AgentError


class ConfigurationView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/configuration"
    suppress_error_fields = True
    idempotency_store_response=False
    audit_resource_type="service"
    def get(self,request,service_id):
        if "service_config.read" not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE","Missing service_config.read scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user)
        from services.api.configuration import ServiceConfigurationAPIView
        self.audit_action="service_config.read"; return ServiceConfigurationAPIView().get(request,service_id)
    @idempotent
    def patch(self,request,service_id):
        if "service_config.write" not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE","Missing service_config.write scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user); from services.api.configuration import ServiceConfigurationAPIView
        self.audit_action="service_config.write"; self.audit_mutating=True; return ServiceConfigurationAPIView().patch(request,service_id)

class EnvironmentView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/environment"
    suppress_error_fields = True
    idempotency_store_response=False
    audit_resource_type="service"
    def get(self,request,service_id):
        if "service_environment.read" not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE","Missing service_environment.read scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user); from services.api.configuration import ServiceEnvironmentAPIView
        self.audit_action="service_environment.read"; return ServiceEnvironmentAPIView().get(request,service_id)
    @idempotent
    def post(self,request,service_id):
        if "service_environment.write" not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE","Missing service_environment.write scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user); from services.api.configuration import ServiceEnvironmentAPIView
        self.audit_action="service_environment.write"; self.audit_mutating=True; return ServiceEnvironmentAPIView().post(request,service_id)
    @idempotent
    def delete(self,request,service_id):
        if "service_environment.write" not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE","Missing service_environment.write scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user); from services.api.configuration import ServiceEnvironmentAPIView
        self.audit_action="service_environment.delete"; self.audit_mutating=True; return ServiceEnvironmentAPIView().delete(request,service_id)

class SecretsView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/secrets"
    suppress_error_fields = True
    idempotency_store_response=False
    audit_resource_type="service"
    def get(self,request,service_id):
        if "service_secrets.read" not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE","Missing service_secrets.read scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user,owner_only=True); from services.api.configuration import ServiceSecretsAPIView
        self.audit_action="service_secrets.read"; return ServiceSecretsAPIView().get(request,service_id)
    @idempotent
    def post(self,request,service_id):
        if "service_secrets.write" not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE","Missing service_secrets.write scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user,owner_only=True); from services.api.configuration import ServiceSecretsAPIView
        self.audit_action="service_secrets.write"; self.audit_mutating=True; return ServiceSecretsAPIView().post(request,service_id)
    @idempotent
    def delete(self,request,service_id):
        if "service_secrets.write" not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE","Missing service_secrets.write scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user,owner_only=True); from services.api.configuration import ServiceSecretsAPIView
        self.audit_action="service_secrets.delete"; self.audit_mutating=True; return ServiceSecretsAPIView().delete(request,service_id)

class EndpointConfigView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/endpoints"
    audit_resource_type="service"
    def get(self,request,service_id):
        if "service_endpoints.read" not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE","Missing service_endpoints.read scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user); from services.api.configuration import ServiceEndpointAPIView
        self.audit_action="service_endpoints.read"; return ServiceEndpointAPIView().get(request,service_id)
    @idempotent
    def post(self,request,service_id):
        if "service_endpoints.write" not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE","Missing service_endpoints.write scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user); from services.api.configuration import ServiceEndpointAPIView
        self.audit_action="service_endpoints.write"; self.audit_mutating=True; return ServiceEndpointAPIView().post(request,service_id)
    @idempotent
    def delete(self,request,service_id):
        if "service_endpoints.write" not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE","Missing service_endpoints.write scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user); from services.api.configuration import ServiceEndpointAPIView
        self.audit_action="service_endpoints.delete"; self.audit_mutating=True; return ServiceEndpointAPIView().delete(request,service_id)

class NetworkAttachmentsView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/networks"
    audit_resource_type="service"
    def get(self,request,service_id):
        if "service_networks.read" not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE","Missing service_networks.read scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user); from services.api.configuration import ServiceNetworksAPIView
        self.audit_action="service_networks.read"; return ServiceNetworksAPIView().get(request,service_id)
    @idempotent
    def post(self,request,service_id):
        if "service_networks.write" not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE","Missing service_networks.write scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user); from services.api.configuration import ServiceNetworksAPIView
        self.audit_action="service_networks.write"; self.audit_mutating=True; return ServiceNetworksAPIView().post(request,service_id)
    @idempotent
    def delete(self,request,service_id):
        if "service_networks.write" not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE","Missing service_networks.write scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user); from services.api.configuration import ServiceNetworksAPIView
        self.audit_action="service_networks.delete"; self.audit_mutating=True; return ServiceNetworksAPIView().delete(request,service_id)

class RevisionListView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/revisions"

    def get(self,request,service_id):
        get_service(service_id,request.user)
        from services.api.configuration import ServiceRevisionAPIView
        return ServiceRevisionAPIView().get(request,service_id)

class RevisionDetailView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/revisions/{revision_id}"

    def get(self,request,service_id,revision_id):
        get_service(service_id,request.user)
        from services.api.configuration import ServiceRevisionDetailAPIView
        return ServiceRevisionDetailAPIView().get(request,service_id,revision_id)

class RevisionRollbackView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/revisions/{revision_id}/rollback"

    @idempotent
    def post(self,request,service_id,revision_id):
        get_service(service_id,request.user,action="can_deploy_add")
        from services.api.configuration import ServiceRevisionRollbackAPIView
        return ServiceRevisionRollbackAPIView().post(__import__("agent.application",fromlist=["RequestProxy"]).RequestProxy(request),service_id,revision_id)

class DatabaseBindingsView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/databases"
    suppress_error_fields = True
    idempotency_store_response = False
    audit_resource_type = "service"

    def _authorize(self, request, service_id, *, write=False):
        scope = "service_config.write" if write else "service_config.read"
        if scope not in set(request.agent.scopes or []):
            raise AgentError(
                "INSUFFICIENT_SCOPE",
                f"Missing {scope} scope.",
                status_code=403,
                failure_domain="authorization",
            )
        get_service(service_id, request.user, action="can_view")

    def _delegate(self, request, service_id, method, *, write=False):
        self._authorize(request, service_id, write=write)
        from services.api.configuration import ServiceDatabaseBindingsAPIView
        handler = ServiceDatabaseBindingsAPIView()
        return getattr(handler, method)(request, service_id)

    def get(self, request, service_id):
        self.audit_action = "service_database_bindings.read"
        return self._delegate(request, service_id, "get")

    @idempotent
    def post(self, request, service_id):
        self.audit_action = "service_database_bindings.write"
        self.audit_mutating = True
        return self._delegate(request, service_id, "post", write=True)

    @idempotent
    def delete(self, request, service_id):
        self.audit_action = "service_database_bindings.delete"
        self.audit_mutating = True
        return self._delegate(request, service_id, "delete", write=True)



class DatabaseCredentialsView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/database-credentials"
    audit_action = "service_database_credentials.read"
    audit_resource_type = "service"
    suppress_error_fields = True
    idempotency_store_response = False

    def get(self, request, service_id):
        from services.models import ServiceDatabaseBinding
        from deployments.common.config import parse_config
        from deployments.core.db_deployer import DB_PLATFORMS, SENSITIVE_CONFIG_KEYS
        from ..application import get_service

        service = get_service(
            service_id,
            request.user,
            action="can_view_db_credentials",
        )
        reveal = str(
            request.query_params.get("reveal") or ""
        ).strip().lower() in {"1", "true", "yes", "on"}

        results = []

        # 1. DatabaseResource bindings attached to a workload Service.
        bindings = (
            ServiceDatabaseBinding.objects
            .filter(service=service)
            .select_related("database", "database__credential")
            .order_by("alias")
        )
        for binding in bindings:
            database = binding.database
            credential = getattr(database, "credential", None)
            password = credential.get_password() if reveal and credential else None
            results.append({
                "type": "managed_database_binding",
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
                    "password_available": bool(
                        credential and getattr(credential, "password_ciphertext", "")
                    ),
                    "revealed": reveal,
                },
            })

        # 2. A first-class database Service stores its native credentials in
        # the active Deploy.config. Read this through the same deployment
        # configuration boundary; never put it into ordinary service_payload().
        platform = str(getattr(getattr(service, "plan", None), "platform", "") or "").strip().lower()
        if platform in DB_PLATFORMS:
            from services.revisioning import get_active_deploy
            deploy = get_active_deploy(service)
            config = parse_config(getattr(deploy, "config", None)) if deploy is not None else {}
            sensitive_keys = sorted(
                key for key in config
                if str(key) in SENSITIVE_CONFIG_KEYS
            )
            credentials = {
                "username": str(config.get("username") or ""),
                "password": str(config.get("password") or "") if reveal else None,
                "root_password": str(config.get("root_password") or "") if reveal else None,
                "password_available": bool(
                    config.get("password") or config.get("root_password")
                ),
                "revealed": reveal,
            }
            results.append({
                "type": "database_service",
                "id": str(service.pk),
                "alias": "service",
                "database": {
                    "id": str(service.pk),
                    "name": service.name,
                    "engine": platform,
                    "host": service.get_docker_service_name(),
                    "port": config.get("port"),
                    "database_name": config.get("database"),
                    "status": service.status,
                    "deployment_id": str(deploy.pk) if deploy is not None else None,
                },
                "credential_keys_present": sensitive_keys,
                "credentials": credentials,
            })

        response = Response({
            "result": "success",
            "service_id": str(service.pk),
            "policy": {
                "service_share_action": "can_view_db_credentials",
                "agent_scope": "service_database_credentials.read",
                "reveal": "query parameter reveal=true returns decrypted password/root_password",
            },
            "results": results,
        })
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response
