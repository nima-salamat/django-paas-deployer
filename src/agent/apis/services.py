from __future__ import annotations

from rest_framework.response import Response
from django.http import HttpResponse
from django.utils import timezone
from .base import AgentSecuredAPIView, AgentPage, idempotent
from .helpers import _ServiceSerializer
from ..application import (
    accessible_service_queryset, create_service, create_service_from_plan, get_service,
    runtime_logs, service_payload, deployment_payload, update_service, call_viewset_action,
)
from ..errors import AgentError


class ServiceListCreateView(AgentPage):
    agent_contract_path = "/agent/v1/services"

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

class ServiceActionView(AgentSecuredAPIView):
    def get_agent_contract_path(self, request):
        return f'/agent/v1/services/{{service_id}}/{self.kwargs.get("action")}'

    audit_resource_type="service"; audit_mutating=True
    @idempotent
    def post(self,request,service_id,action):
        from services.api.runtime import start_service_apiview, stop_service_apiview, restart_service_apiview
        from services.api.volume_files import purge_service_runtime_apiview
        from ..application import call_runtime_api
        share_action = {"start": "can_start", "stop": "can_stop", "restart": "can_restart", "purge-runtime": "can_purge", "rebuild": "can_rebuild"}[action]
        get_service(service_id, request.user, action=share_action)
        if action == "rebuild":
            fn = start_service_apiview
            data = {"service_id": str(service_id), "force_rebuild": True}
        else:
            fn = {"start": start_service_apiview, "stop": stop_service_apiview, "restart": restart_service_apiview, "purge-runtime": purge_service_runtime_apiview}[action]
            data = {"service_id": str(service_id)}
        self.audit_action = f"services.{action.replace('-', '_')}"
        return call_runtime_api(fn, request, service_id, data=data)

class ServiceStatusView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/status"

    def get(self,request,service_id):
        get_service(service_id,request.user,action="can_view")
        from services.api.runtime import service_status_apiview
        from deployments.core.swarm import swarm_enabled
        from ..application import call_runtime_api
        return call_runtime_api(service_status_apiview, request, service_id, data={"service_id":str(service_id)})

class ServiceLogsView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/logs"

    def get(self,request,service_id):
        service=get_service(service_id,request.user,action="can_view_logs")
        data=runtime_logs(service.pk,request)
        events=[{"timestamp":e.get("ts"),"level":e.get("level"),"source":"runtime","stream":e.get("stream"),"message":e.get("message"),"service_id":str(service.pk),"deployment_id":e.get("deployment_id"),"cursor":e.get("cursor")} for e in data.get("events",[])]
        return Response({"result":"success","source":"runtime","service_id":str(service.pk),"events":events,"next_cursor":data.get("next_cursor"),"prev_cursor":data.get("prev_cursor"),"has_more_older":data.get("has_more_older"),"has_more_newer":data.get("has_more_newer"),"count":len(events)})

class ServiceLogsExportView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/services/{service_id}/logs/export"

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



class ServiceMetricsView(AgentSecuredAPIView):
    """Expose observed runtime CPU/RAM metrics plus the immutable plan ceiling."""

    agent_contract_path = "/agent/v1/services/{service_id}/metrics"
    audit_action = "services.metrics.read"
    audit_resource_type = "service"

    def get(self, request, service_id):
        service = get_service(service_id, request.user, action="can_view_metrics")
        from services.api.runtime import service_status_apiview
        from ..application import call_runtime_api

        response = call_runtime_api(
            service_status_apiview,
            request,
            service_id,
            data={"service_id": str(service_id)},
        )
        if getattr(response, "status_code", 500) >= 400:
            return response

        payload = dict(getattr(response, "data", {}) or {})
        cpu = payload.get("cpu")
        memory = payload.get("ram")
        plan = getattr(service, "plan", None)
        metrics_available = payload.get("metrics_available")
        return Response({
            "result": "success",
            "service_id": str(service.pk),
            "observed_at": timezone.now(),
            "runtime": {
                "backend": "docker-swarm" if swarm_enabled() else "docker",
                "running": bool(payload.get("running")),
                "metrics_available": metrics_available,
                "metrics_reason": payload.get("metrics_reason"),
            },
            "usage": {
                "cpu_percent": cpu,
                "cpu_cores": payload.get("cpu_cores"),
                "memory_percent": memory,
                "memory_usage_bytes": payload.get("memory_usage_bytes"),
            },
            "limits": {
                "cpu_vcpu": float(plan.max_cpu) if plan is not None else payload.get("cpu_limit_cores"),
                "memory_mb": int(float(plan.max_ram)) if plan is not None else (
                    int(float(payload["memory_limit_bytes"]) / (1024 * 1024))
                    if payload.get("memory_limit_bytes") not in (None, "")
                    else None
                ),
                "memory_limit_bytes": payload.get("memory_limit_bytes"),
                "cpu_limit_cores": payload.get("cpu_limit_cores"),
            },
        })


