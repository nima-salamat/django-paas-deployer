from __future__ import annotations

from rest_framework.response import Response
from django.http import HttpResponse
from .base import AgentSecuredAPIView, AgentPage, idempotent
from .helpers import _DeploymentSerializer
from ..application import (
    call_api_view_handler, call_viewset_action, deployment_payload, deployment_queryset,
    get_deployment, get_service, upload_deployment_zip,
)


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

