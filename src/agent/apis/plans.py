from __future__ import annotations

from rest_framework.response import Response
from .base import AgentSecuredAPIView, AgentPage, idempotent
from .helpers import _PlanSerializer, _plan_payload
from ..application import create_service_from_plan


class PlanListView(AgentPage):
    agent_contract_path = "/agent/v1/plans"

    def get(self,request):
        from plans.models import Plan
        return self.paginate(request,Plan.objects.all().order_by("platform","name"),_PlanSerializer)

class PlanDetailView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/plans/{plan_id}"

    def get(self,request,plan_id):
        from plans.models import Plan
        plan=Plan.objects.filter(pk=plan_id).first()
        if not plan:raise AgentError("PLAN_NOT_FOUND","Plan not found.",status_code=404,failure_domain="resource")
        return Response({"result":"success","plan":_plan_payload(plan)})

class PlanManagementView(AgentSecuredAPIView):
    def get_agent_contract_path(self, request):
        return "/agent/v1/plans/manage/{plan_id}" if self.kwargs.get("plan_id") else "/agent/v1/plans/manage"


    @idempotent
    def post(self,request):
        from ..application import manage_plan
        plan=manage_plan(request,"create",data=dict(request.data))
        self.audit_action="plans.create"
        return Response({"result":"success","plan":_plan_payload(plan)},status=201)

    @idempotent
    def patch(self,request,plan_id):
        from ..application import manage_plan
        plan=manage_plan(request,"update",plan_id=plan_id,data=dict(request.data))
        self.audit_action="plans.update"
        return Response({"result":"success","plan":_plan_payload(plan)})

    @idempotent
    def delete(self,request,plan_id):
        from ..application import manage_plan
        manage_plan(request,"destroy",plan_id=plan_id)
        self.audit_action="plans.delete"
        return Response({"result":"success","plan_id":str(plan_id)},status=200)

class PlanApplyView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/plans/{plan_id}/apply"
    """Create a Service from an existing Plan through the normal Service API boundary."""

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

