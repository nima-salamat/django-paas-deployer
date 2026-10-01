
from __future__ import annotations

import time
from functools import wraps

from django.http import HttpResponse, JsonResponse
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .application import (
    call_api_view_handler,
    call_viewset_action,
    create_enrollment,
    create_service,
    deployment_payload,
    deployment_queryset,
    get_deployment,
    get_service,
    redact_shell_result,
    runtime_logs,
    service_payload,
    update_service,
    upload_deployment_zip,
    accessible_service_queryset,
    ensure_service_access,
    create_service_from_plan,
)
from .authentication import AgentTokenAuthentication
from .errors import AgentError, agent_error_response, normalize_exception
from .models import Agent
from .permissions import AgentScopePermission, IsAgentAuthenticated
from .scopes import SERVICE_SCOPES, DESTRUCTIVE_SCOPES, HIGH_RISK_SCOPES, SCOPE_LABELS, scope_categories
from .security import get_request_id, sanitize_metadata
from .throttling import AgentRateThrottle


def complete_error(response, request, *, suppress_sensitive_fields=False):
    status_code = int(getattr(response, "status_code", 500))
    data = getattr(response, "data", None)
    if status_code >= 400:
        if isinstance(data, dict) and data.get("result") == "error" and data.get("code"):
            body = dict(data)
        else:
            if status_code == 401: code, domain, retry = "AUTHENTICATION_REQUIRED", "authentication", False
            elif status_code == 403: code, domain, retry = "PERMISSION_DENIED", "authorization", False
            elif status_code == 404: code, domain, retry = "RESOURCE_NOT_FOUND", "resource", False
            elif status_code == 409: code, domain, retry = "CONFLICT", "resource", False
            elif status_code == 413: code, domain, retry = "UPLOAD_TOO_LARGE", "storage", False
            elif status_code == 422: code, domain, retry = "UNSUPPORTED_CAPABILITY", "request", False
            elif status_code == 429: code, domain, retry = "RATE_LIMITED", "infrastructure", True
            else: code, domain, retry = "INVALID_REQUEST" if status_code < 500 else "INTERNAL_ERROR", "request" if status_code < 500 else "runtime", False
            detail = data.get("detail") or data.get("error") if isinstance(data, dict) else str(data or "")
            body = {
                "result": "error", "code": code, "detail": detail or "Request failed.",
                "request_id": getattr(request, "agent_request_id", None), "retryable": retry,
                "failure_domain": domain, "visibility": "client", "resource_effect": "unchanged", "certainty": "known",
            }
            if isinstance(data, dict):
                for key in ("errors", "action", "missing_scopes", "supported_inputs"):
                    if key in data:
                        body[key] = sanitize_metadata(data[key])
        if suppress_sensitive_fields:
            from .security import extract_sensitive_request_values, sanitize_error_payload
            body = sanitize_error_payload(
                body,
                secret_values=extract_sensitive_request_values(getattr(request, "data", {})),
            )
        response.data = sanitize_metadata(body)
    return response


def idempotent(fn):
    @wraps(fn)
    def wrapped(self, request, *args, **kwargs):
        from .application import begin_idempotency, complete_idempotency, abandon_idempotency
        row = replay = None
        try:
            row, replay = begin_idempotency(request.agent, request)
            if replay is not None:
                response = Response(replay.response_body or {}, status=replay.status_code or 200)
                self.audit_metadata = {"idempotent_replay": True}
                return response
            response = fn(self, request, *args, **kwargs)
            complete_idempotency(
                row,
                response,
                store_body=bool(getattr(self, "idempotency_store_response", True)),
            )
            return response
        except Exception:
            abandon_idempotency(row)
            raise
    return wrapped


def _audit_resource_id(kwargs, data):
    for key in ("service_id", "deployment_id", "revision_id", "volume_id", "network_id", "plan_id"):
        value = kwargs.get(key)
        if value:
            return str(value)
    if isinstance(data, dict):
        if data.get("id"):
            return str(data["id"])
        for container_key in ("service", "deployment", "revision", "resource"):
            value = data.get(container_key)
            if isinstance(value, dict) and value.get("id"):
                return str(value["id"])
    return ""



class AgentAPIView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [AgentRateThrottle]
    throttle_scope = "read"
    required_scopes = ()
    required_scopes_by_method = {}
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    audit_action = "agent.request"
    audit_resource_type = ""
    audit_mutating = False
    idempotency_store_response = True
    suppress_error_fields = False
    agent_contract_path = None

    def get_agent_contract_path(self, request):
        return self.agent_contract_path

    def initial(self, request, *args, **kwargs):
        request.agent_request_id = get_request_id(request)
        self._started_at = time.monotonic()
        super().initial(request, *args, **kwargs)

    def handle_exception(self, exc):
        if isinstance(exc, AgentError):
            return agent_error_response(exc)
        return normalize_exception(exc, super().handle_exception(exc))

    def finalize_response(self, request, response, *args, **kwargs):
        from .application import audit
        response = complete_error(response, request, suppress_sensitive_fields=bool(getattr(self, "suppress_error_fields", False)))
        try:
            response["X-Request-ID"] = str(request.agent_request_id)
            if isinstance(getattr(response, "data", None), dict) and response.data.get("result") == "error":
                response.data["request_id"] = str(request.agent_request_id)
        except Exception:
            pass
        try:
            status_code = int(response.status_code)
            success = 200 <= status_code < 400
            data = response.data if isinstance(response.data, dict) else {}
            audit(
                request=request,
                action=self.audit_action,
                success=success,
                status_code=status_code,
                resource_type=self.audit_resource_type,
                resource_id=_audit_resource_id(kwargs, data),
                error_code=str(data.get("code") or ""),
                failure_domain=str(data.get("failure_domain") or ""),
                retryability=bool(data.get("retryable")),
                resource_effect=("queued" if status_code == 202 else "changed" if self.audit_mutating and success else "unchanged"),
                duration_ms=int(max(0, (time.monotonic() - self._started_at) * 1000)),
                metadata=getattr(self, "audit_metadata", {}),
            )
        except Exception:
            pass
        return super().finalize_response(request, response, *args, **kwargs)


class AgentPublicAPIView(AgentAPIView):
    throttle_scope = "exchange"


class AgentSecuredAPIView(AgentAPIView):
    authentication_classes = [AgentTokenAuthentication]
    permission_classes = [IsAgentAuthenticated, AgentScopePermission]


class AgentRootView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1"
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
    audit_action = "credential.exchange"
    def post(self, request):
        from .application import exchange_enrollment, audit
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
                "services": {scope.split(".",1)[1]: scope in s for scope in SERVICE_SCOPES},
                "plans": {"read":"plans.read" in s,"apply":"plans.apply" in s and "services.create" in s,"manage":"plans.manage" in s},
                "deployments": {x.split(".",1)[1]: x in s for x in (
                    "deployments.read","deployments.create","deployments.upload","deployments.start","deployments.cancel",
                    "deployments.redeploy","deployments.rebuild","deployments.rollback","deployments.delete")},
                "logs": {"deployment_read":"deployments.logs.read" in s,"deployment_export":"deployments.logs.export" in s,"runtime_read":"service_logs.read" in s,"runtime_export":"service_logs.export" in s},
                "shell": {"read":"shell.read" in s,"execute":"shell.execute" in s,"replace":"shell.replace" in s,"files_read":"shell.files.read" in s,"files_write":"shell.files.write" in s},
                "agent": {"manifest_generate":"agent.manifest.generate" in s},
            },
            "deployment_inputs": {"archive_zip": True, "database_native": True, "git": False, "existing_image": False},
            "logs": {
                "deployment": {"model":"DeployLog","database_alias":"deployment_logs"},
                "runtime": {"models":["ServiceLogStream","ServiceLogEntry"],"database_alias":"deployment_logs"},
            },
            "pagination": {"default_page_size": 25, "max_page_size": 100},
            "idempotency": {"header":"Idempotency-Key","ttl_hours":24,"important_mutations":True},
            "high_risk_scopes": sorted(HIGH_RISK_SCOPES & s),
            "unsupported": ["Git deployment input", "existing-image deployment input", "host shell", "raw Docker API"],
            "confirmation": {"shell_destructive_commands": True, "deployment_rebuild": "deployments.rebuild" in s, "deployment_rollback": "deployments.rollback" in s},
        })


class AgentManifestView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/agent.md"
    required_scopes = ("agent.manifest.generate",)
    throttle_scope = "mutation"
    audit_action = "agent.manifest.generate"
    def get(self, request):
        from .manifest import render_agent_manifest
        enrollment, row = create_enrollment(request.agent, request=request)
        self.audit_metadata = {"enrollment_prefix": row.token_prefix, "enrollment_expires_at": row.expires_at.isoformat()}
        response = HttpResponse(
            render_agent_manifest(request.agent, enrollment, request=request),
            content_type="text/markdown; charset=utf-8",
        )
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class AgentOpenAPIView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/openapi.json"
    audit_action = "agent.openapi.read"
    def get(self, request):
        from .openapi import build_openapi
        return JsonResponse(build_openapi(request.agent, request=request), json_dumps_params={"indent":2})


class AgentPage(AgentSecuredAPIView):
    page_size = 25
    def paginate(self, request, queryset, serializer):
        p = PageNumberPagination()
        p.page_size = self.page_size; p.page_size_query_param = "page_size"; p.max_page_size = 100
        page = p.paginate_queryset(queryset, request)
        return p.get_paginated_response(serializer(page, many=True).data) if page is not None else Response({"results": serializer(queryset, many=True).data})


class ServiceListCreateView(AgentPage):
    agent_contract_path = "/agent/v1/services"
    required_scopes_by_method = {"GET":("services.read",),"POST":("services.create",)}
    audit_resource_type = "service"
    def get(self, request):
        self.audit_action = "services.list"
        return self.paginate(request, accessible_service_queryset(request.user), _ServiceSerializer)
    @idempotent
    def post(self, request):
        self.audit_action = "services.create"; self.audit_mutating = True
        service = create_service(request, dict(request.data))
        return Response({"result":"success","service":service_payload(service)}, status=201)


class ServiceDetailView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}"
    required_scopes_by_method = {"GET":("services.read",),"PATCH":("services.update",),"DELETE":("services.delete",)}
    audit_resource_type = "service"
    def get(self, request, service_id):
        self.audit_action = "services.retrieve"
        return Response({"result":"success","service":service_payload(get_service(service_id,request.user))})
    @idempotent
    def patch(self, request, service_id):
        self.audit_action="services.update"; self.audit_mutating=True
        result = update_service(request, service_id, dict(request.data))
        return result if isinstance(result,Response) else Response(result)
    @idempotent
    def delete(self, request, service_id):
        from services.api.user_services import ServiceViewSet
        service=get_service(service_id,request.user)
        response=call_viewset_action(ServiceViewSet,"destroy",request,pk=service.pk)
        self.audit_action="services.delete"; self.audit_mutating=True
        return response


class ServiceFromPlanView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/from-plan"
    required_scopes=("services.create","plans.apply")
    audit_action="services.create_from_plan"; audit_resource_type="service"; audit_mutating=True

    @idempotent
    def post(self,request):
        service, network = create_service_from_plan(request, dict(request.data))
        self.audit_metadata = {
            **getattr(self, "audit_metadata", {}),
            "service_id": str(service.pk),
            "plan_id": str(service.plan_id),
            **({"network_id": str(network.pk)} if network is not None else {}),
        }
        return Response({"result":"success","service":service_payload(service)},status=201)


class PlanApplyView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/plans/{plan_id}/apply"
    """Create a Service from an existing Plan through the normal Service API boundary."""
    required_scopes=("plans.apply","services.create")
    audit_action="plans.apply"
    audit_resource_type="plan"
    audit_mutating=True

    @idempotent
    def post(self,request,plan_id):
        service, network = create_service_from_plan(
            request,
            dict(request.data),
            plan_id=plan_id,
        )
        self.audit_metadata = {
            "plan_id": str(plan_id),
            "service_id": str(service.pk),
            **({"network_id": str(network.pk)} if network is not None else {}),
        }
        return Response(
            {"result":"success","service":service_payload(service)},
            status=201,
        )


class ServiceActionView(AgentSecuredAPIView):
    def get_agent_contract_path(self, request):
        return f"/agent/v1/services/{{service_id}}/{self.kwargs.get("action")}"
    action_scopes={"start":"services.start","stop":"services.stop","restart":"services.restart","purge-runtime":"services.purge"}
    share_actions={"start":"can_start","stop":"can_stop","restart":"can_restart","purge-runtime":"can_purge"}
    required_scopes=()
    audit_resource_type="service"; audit_mutating=True
    @idempotent
    def post(self,request,service_id,action):
        from services.api.runtime import start_service_apiview, stop_service_apiview, restart_service_apiview
        from services.api.volume_files import purge_service_runtime_apiview
        from .application import call_runtime_api
        scope=self.action_scopes[action]
        if scope not in set(request.agent.scopes or []): raise AgentError("INSUFFICIENT_SCOPE",f"Missing {scope} scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user,action="can_view")
        fn={"start":start_service_apiview,"stop":stop_service_apiview,"restart":restart_service_apiview,"purge-runtime":purge_service_runtime_apiview}[action]
        self.audit_action=f"services.{action.replace('-','_')}"
        return call_runtime_api(fn, request, service_id, data={"service_id":str(service_id)})


class ServiceStatusView(AgentSecuredAPIView):
    required_scopes=("services.read",); audit_action="services.status"; audit_resource_type="service"
    def get(self,request,service_id):
        get_service(service_id,request.user,action="can_view")
        from services.api.runtime import service_status_apiview
        from .application import call_runtime_api
        return call_runtime_api(service_status_apiview, request, service_id, data={"service_id":str(service_id)})


class PlanListView(AgentPage):
    agent_contract_path = "/agent/v1/plans"
    required_scopes=("plans.read",); audit_action="plans.list"; audit_resource_type="plan"
    def get(self,request):
        from plans.models import Plan
        return self.paginate(request,Plan.objects.all().order_by("platform","name"),_PlanSerializer)


class PlanDetailView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/plans/{plan_id}"
    required_scopes=("plans.read",); audit_action="plans.retrieve"; audit_resource_type="plan"
    def get(self,request,plan_id):
        from plans.models import Plan
        plan=Plan.objects.filter(pk=plan_id).first()
        if not plan:raise AgentError("PLAN_NOT_FOUND","Plan not found.",status_code=404,failure_domain="resource")
        return Response({"result":"success","plan":_plan_payload(plan)})


class PlanManagementView(AgentSecuredAPIView):
    def get_agent_contract_path(self, request):
        return "/agent/v1/plans/manage/{plan_id}" if self.kwargs.get("plan_id") else "/agent/v1/plans/manage"
    required_scopes=("plans.manage",); audit_resource_type="plan"; audit_mutating=True

    @idempotent
    def post(self,request):
        from .application import manage_plan
        plan=manage_plan(request,"create",data=dict(request.data))
        self.audit_action="plans.create"
        return Response({"result":"success","plan":_plan_payload(plan)},status=201)

    @idempotent
    def patch(self,request,plan_id):
        from .application import manage_plan
        plan=manage_plan(request,"update",plan_id=plan_id,data=dict(request.data))
        self.audit_action="plans.update"
        return Response({"result":"success","plan":_plan_payload(plan)})

    @idempotent
    def delete(self,request,plan_id):
        from .application import manage_plan
        manage_plan(request,"destroy",plan_id=plan_id)
        self.audit_action="plans.delete"
        return Response({"result":"success","plan_id":str(plan_id)},status=200)
class NetworkListCreateView(AgentPage):
    agent_contract_path = "/agent/v1/networks"
    required_scopes_by_method={"GET":("service_networks.read",),"POST":("service_networks.write",)}
    audit_resource_type="network"
    def get(self,request):
        from .application import network_queryset
        self.audit_action="networks.list"; return self.paginate(request,network_queryset(request.user),_NetworkSerializer)
    @idempotent
    def post(self,request):
        from .application import create_network,network_payload
        network=create_network(request,dict(request.data)); self.audit_action="networks.create"; self.audit_mutating=True
        return Response({"result":"success","network":network_payload(network)},status=201)


class NetworkDetailView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/networks/{network_id}"
    required_scopes_by_method={"GET":("service_networks.read",),"PATCH":("service_networks.write",),"DELETE":("service_networks.write",)}
    audit_resource_type="network"
    def get(self,request,network_id):
        from .application import network_queryset,network_payload
        network=network_queryset(request.user).filter(pk=network_id).first()
        if not network:raise AgentError("NETWORK_NOT_FOUND","Network not found.",status_code=404,failure_domain="resource")
        self.audit_action="networks.retrieve"; return Response({"result":"success","network":network_payload(network)})
    @idempotent
    def patch(self,request,network_id):
        from .application import network_queryset,update_network,network_payload
        network=network_queryset(request.user).filter(pk=network_id).first()
        if not network:raise AgentError("NETWORK_NOT_FOUND","Network not found.",status_code=404)
        network=update_network(request,network.pk,dict(request.data))
        if isinstance(network, Response):
            return network
        self.audit_action="networks.update"; self.audit_mutating=True
        return Response({"result":"success","network":network_payload(network)})
    @idempotent
    def delete(self,request,network_id):
        from .application import network_queryset
        from services.api.user_services import PrivateNetworkViewSet
        network=network_queryset(request.user).filter(pk=network_id).first()
        if not network:raise AgentError("NETWORK_NOT_FOUND","Network not found.",status_code=404)
        response=call_viewset_action(PrivateNetworkViewSet,"destroy",request,pk=network.pk)
        self.audit_action="networks.delete"; self.audit_mutating=True; return response


class VolumeListCreateView(AgentPage):
    agent_contract_path = "/agent/v1/volumes"
    required_scopes_by_method={"GET":("service_volumes.read",),"POST":("service_volumes.write",)}
    audit_resource_type="volume"
    def get(self,request):
        from services.api.user_services import VolumeViewSet
        proxy=call_viewset_action
        view=VolumeViewSet(); view.request=request; view.action="list"; qs=view.get_queryset().select_related("service")
        self.audit_action="volumes.list"; return self.paginate(request,qs,_VolumeSerializer)
    @idempotent
    def post(self,request):
        from services.api.user_services import VolumeViewSet
        response=call_viewset_action(VolumeViewSet,"create",request,data=dict(request.data))
        self.audit_action="volumes.create"; self.audit_mutating=True; return response


class VolumeDetailView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/volumes/{volume_id}"
    required_scopes_by_method={"GET":("service_volumes.read",),"PATCH":("service_volumes.write",),"DELETE":("service_volumes.write",)}
    audit_resource_type="volume"
    def _get(self,request,volume_id):
        from services.api.user_services import VolumeViewSet
        view=VolumeViewSet(); view.request=request; view.action="retrieve"; return view.get_queryset().filter(pk=volume_id).first()
    def get(self,request,volume_id):
        v=self._get(request,volume_id)
        if not v:raise AgentError("VOLUME_NOT_FOUND","Volume not found.",status_code=404)
        self.audit_action="volumes.retrieve"; return Response({"result":"success","volume":_volume_payload(v)})
    @idempotent
    def patch(self,request,volume_id):
        from services.api.user_services import VolumeViewSet
        v=self._get(request,volume_id)
        if not v:raise AgentError("VOLUME_NOT_FOUND","Volume not found.",status_code=404)
        response=call_viewset_action(VolumeViewSet,"update",request,pk=v.pk,data=dict(request.data))
        self.audit_action="volumes.update"; self.audit_mutating=True; return response
    @idempotent
    def delete(self,request,volume_id):
        from services.api.user_services import VolumeViewSet
        v=self._get(request,volume_id)
        if not v:raise AgentError("VOLUME_NOT_FOUND","Volume not found.",status_code=404)
        response=call_viewset_action(VolumeViewSet,"destroy",request,pk=v.pk)
        self.audit_action="volumes.delete"; self.audit_mutating=True; return response


class DeploymentListCreateView(AgentPage):
    agent_contract_path = "/agent/v1/deployments"
    required_scopes_by_method={"GET":("deployments.read",),"POST":("deployments.create",)}
    audit_resource_type="deployment"
    def get(self,request): self.audit_action="deployments.list"; return self.paginate(request,deployment_queryset(request.user),_DeploymentSerializer)
    @idempotent
    def post(self,request):
        from .application import create_deployment
        d=create_deployment(request,dict(request.data)); self.audit_action="deployments.create"; self.audit_mutating=True
        return Response({"result":"success","deployment":deployment_payload(d)},status=201)


class DeploymentDetailView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/deployments/{deployment_id}"
    required_scopes_by_method={"GET":("deployments.read",),"DELETE":("deployments.delete",)}
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
    required_scopes=("deployments.upload",); throttle_scope="upload"; audit_action="deployments.upload"; audit_resource_type="deployment"; audit_mutating=True
    @idempotent
    def post(self,request,deployment_id):
        d=upload_deployment_zip(request,deployment_id)
        return Response({"result":"success","deployment":deployment_payload(d)})


class DeploymentActionView(AgentSecuredAPIView):
    def get_agent_contract_path(self, request):
        return f"/agent/v1/deployments/{{deployment_id}}/{self.kwargs.get("action")}"
    action_scopes={"start":"deployments.start","cancel":"deployments.cancel","redeploy":"deployments.redeploy","rebuild":"deployments.rebuild"}
    required_scopes=(); throttle_scope="deployment"; audit_resource_type="deployment"; audit_mutating=True
    @idempotent
    def post(self,request,deployment_id,action):
        response=__import__("agent.application",fromlist=["deployment_action"]).deployment_action(request,deployment_id,action)
        self.audit_action=f"deployments.{action}"; return response


class DeploymentRollbackView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/deployments/{deployment_id}/rollback"
    required_scopes=("deployments.rollback",); audit_action="deployments.rollback"; audit_resource_type="deployment"; audit_mutating=True; throttle_scope="deployment"
    @idempotent
    def post(self,request,deployment_id):
        d=get_deployment(deployment_id,request.user,action="can_deploy_add")
        if not d.revision_id:raise AgentError("ROLLBACK_UNAVAILABLE","Deployment has no immutable revision.",status_code=409,failure_domain="resource")
        from services.api.configuration import ServiceRevisionRollbackAPIView
        return ServiceRevisionRollbackAPIView().post(__import__("agent.application",fromlist=["RequestProxy"]).RequestProxy(request),d.service_id,d.revision_id)


class DeploymentLogsView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/deployments/{deployment_id}/logs"
    required_scopes=("deployments.logs.read",); audit_action="deployments.logs.read"; audit_resource_type="deployment"
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
    required_scopes=("deployments.logs.export",); audit_action="deployments.logs.export"; audit_resource_type="deployment"
    def get(self,request,deployment_id):
        from deploy.apis import deploy_logs_export_apiview
        d=get_deployment(deployment_id,request.user)
        return call_api_view_handler(deploy_logs_export_apiview,request,"get",d.pk)


class ServiceLogsView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/logs"
    required_scopes=("service_logs.read",); audit_action="service_logs.read"; audit_resource_type="service"
    def get(self,request,service_id):
        service=get_service(service_id,request.user,action="can_view_logs")
        data=runtime_logs(service.pk,request)
        events=[{"timestamp":e.get("ts"),"level":e.get("level"),"source":"runtime","stream":e.get("stream"),"message":e.get("message"),"service_id":str(service.pk),"deployment_id":e.get("deployment_id"),"cursor":e.get("cursor")} for e in data.get("events",[])]
        return Response({"result":"success","source":"runtime","service_id":str(service.pk),"events":events,"next_cursor":data.get("next_cursor"),"prev_cursor":data.get("prev_cursor"),"has_more_older":data.get("has_more_older"),"has_more_newer":data.get("has_more_newer"),"count":len(events)})


class ServiceLogsExportView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/logs/export"
    required_scopes=("service_logs.export",); audit_action="service_logs.export"; audit_resource_type="service"
    def get(self,request,service_id):
        service=get_service(service_id,request.user,action="can_view_logs")
        from logs.query import export_logs
        from django.utils.dateparse import parse_datetime
        def dt(k):
            raw=request.query_params.get(k)
            if not raw:return None
            value=parse_datetime(raw)
            if value is None:raise AgentError("INVALID_REQUEST","Invalid timestamp.",status_code=400)
            return value
        limit=min(max(int(request.query_params.get("limit") or 5000),1),10000); fmt=(request.query_params.get("format") or "txt").lower()
        ctype,body=export_logs(service.pk,fmt=fmt if fmt in {"txt","jsonl"} else "txt",from_ts=dt("from"),to_ts=dt("to"),level=request.query_params.get("level") or "",stream=request.query_params.get("stream") or "",q=request.query_params.get("q") or "",limit=limit)
        response=HttpResponse(body,content_type=ctype); response["Content-Disposition"]=f'attachment; filename="service-{service.pk}-logs.{"jsonl" if fmt=="jsonl" else "txt"}"'; return response


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
    required_scopes=("services.read",); audit_action="revisions.list"; audit_resource_type="revision"
    def get(self,request,service_id):
        get_service(service_id,request.user)
        from services.api.configuration import ServiceRevisionAPIView
        return ServiceRevisionAPIView().get(request,service_id)


class RevisionDetailView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/revisions/{revision_id}"
    required_scopes=("services.read",); audit_action="revisions.retrieve"; audit_resource_type="revision"
    def get(self,request,service_id,revision_id):
        get_service(service_id,request.user)
        from services.api.configuration import ServiceRevisionDetailAPIView
        return ServiceRevisionDetailAPIView().get(request,service_id,revision_id)


class RevisionRollbackView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/revisions/{revision_id}/rollback"
    required_scopes=("deployments.rollback",); audit_action="revisions.rollback"; audit_resource_type="revision"; audit_mutating=True
    @idempotent
    def post(self,request,service_id,revision_id):
        get_service(service_id,request.user,action="can_deploy_add")
        from services.api.configuration import ServiceRevisionRollbackAPIView
        return ServiceRevisionRollbackAPIView().post(__import__("agent.application",fromlist=["RequestProxy"]).RequestProxy(request),service_id,revision_id)


class ShellInfoView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/shell"
    required_scopes=("shell.read",); throttle_scope="shell"; audit_action="shell.info"; audit_resource_type="service"
    def get(self,request,service_id):
        service=get_service(service_id,request.user,action="can_view")
        from services.shell import command_catalog,_platform_for_service,can_use_advanced_shell
        allowed=ensure_service_access(service,request.user,action="can_shell")
        return Response({"result":"success","service_id":str(service.pk),"enabled":bool(allowed is not False and "shell.execute" in set(request.agent.scopes or [])),"platform":_platform_for_service(service),"advanced_interactive":bool(can_use_advanced_shell(service,request.user)),"commands":command_catalog(_platform_for_service(service)),"policy":{"host_shell":False,"shell_operators":False,"destructive_commands_require_confirmation":True,"path_confinement":True,"output_limits":True,"session_ttl":True}})


class ShellSessionView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/shell/sessions"
    required_scopes=("shell.read","shell.execute"); throttle_scope="shell"; audit_action="shell.session.create"; audit_resource_type="service"; audit_mutating=True
    def post(self,request,service_id):
        service=get_service(service_id,request.user,action="can_shell")
        from services.shell import create_session
        session,token=create_session(service,request.user,request.data.get("workdir"))
        self.audit_metadata={"session_id":str(session.pk),"service_id":str(service.pk)}
        return Response({"result":"success","session_id":str(session.pk),"token":token,"token_type":"Shell","platform":session.platform,"cwd":session.workdir,"expires_at":session.expires_at},status=201)


class ShellCommandView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/shell/sessions/{session_id}/commands"
    required_scopes=("shell.execute",); throttle_scope="shell"; audit_action="shell.command"; audit_resource_type="service"; audit_mutating=True
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
        return Response({"result":"success","command":safe.get("command") or command,"exit_code":safe.get("exit_code"),"stdout":safe.get("stdout"),"stderr":safe.get("stderr"),"duration_ms":safe.get("duration_ms"),"cwd":safe.get("cwd") or session.workdir,"session_id":str(session.pk)})


class ShellCloseView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/shell/sessions/{session_id}/close"
    required_scopes=("shell.execute",); throttle_scope="shell"; audit_action="shell.session.close"; audit_resource_type="service"; audit_mutating=True
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
    required_scopes=("shell.replace",); throttle_scope="shell"; audit_action="shell.session.replace"; audit_resource_type="service"; audit_mutating=True
    def post(self,request,service_id):
        service=get_service(service_id,request.user,action="can_shell")
        ensure_service_access(service,request.user,action="can_shell_replace")
        if request.data.get("confirm") is not True:raise AgentError("CONFIRMATION_REQUIRED","confirm=true is required to replace the active shell session.",status_code=409,failure_domain="authorization")
        from services.shell import terminate_active_session,create_session
        old=terminate_active_session(service,actor=request.user); session,token=create_session(service,request.user,request.data.get("workdir"))
        return Response({"result":"success","replaced":bool(old),"previous_session_id":str(old.pk) if old else None,"session_id":str(session.pk),"token":token,"expires_at":session.expires_at,"cwd":session.workdir},status=201)


class ShellFileView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/shell/files"
    throttle_scope="shell"; audit_resource_type="service"
    def post(self,request,service_id):
        action=str(request.data.get("action") or "read").lower()
        scope="shell.files.write" if action in {"write","delete","rename","create","create_folder"} else "shell.files.read"
        if scope not in set(request.agent.scopes or []):raise AgentError("INSUFFICIENT_SCOPE",f"Missing {scope} scope.",status_code=403,failure_domain="authorization")
        get_service(service_id,request.user,action="can_shell")
        from services.api.shell import shell_file_apiview
        self.audit_action=f"shell.file.{action}"; self.audit_mutating=scope.endswith("write")
        return call_api_view_handler(shell_file_apiview,request,"post",service_id)


class _ServiceSerializer:
    def __init__(self,instance,many=False): self.data=[service_payload(x) for x in instance] if many else service_payload(instance)
class _PlanSerializer:
    def __init__(self,instance,many=False): self.data=[_plan_payload(x) for x in instance] if many else _plan_payload(instance)
class _NetworkSerializer:
    def __init__(self,instance,many=False): self.data=[_network_payload(x) for x in instance] if many else _network_payload(instance)
class _VolumeSerializer:
    def __init__(self,instance,many=False): self.data=[_volume_payload(x) for x in instance] if many else _volume_payload(instance)
class _DeploymentSerializer:
    def __init__(self,instance,many=False): self.data=[deployment_payload(x) for x in instance] if many else deployment_payload(instance)

def _plan_payload(p):
    return {"id":str(p.pk),"name":p.name,"platform":p.platform,"plan_type":p.plan_type,"max_cpu":p.max_cpu,"max_ram":p.max_ram,"max_storage":p.max_storage,"storage_type":p.storage_type,"price_per_hour":p.price_per_hour,"price_per_day":p.price_per_day,"price_per_month":p.price_per_month,"logging":{"retention_days":p.log_retention_days,"storage_mb":p.log_storage_mb,"persistent":p.persistent_logging,"realtime":p.realtime_logging}}

def _network_payload(n):
    return {"id":str(n.pk),"name":n.name,"description":n.description,"created_at":n.created_at,"updated_at":n.updated_at}

def _volume_payload(v):
    return {"id":str(v.pk),"name":v.name,"service_id":str(v.service_id) if v.service_id else None,"user_id":str(v.user_id),"size_mb":v.size_mb,"default_bind":v.default_bind,"default_mode":v.default_mode,"released_at":getattr(v,"released_at",None),"reclaim_attempted_at":getattr(v,"reclaim_attempted_at",None),"reclaim_error":getattr(v,"reclaim_error","")}


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
