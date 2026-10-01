from __future__ import annotations

from rest_framework.response import Response
from .base import AgentSecuredAPIView, AgentPage, idempotent
from .helpers import _VolumeSerializer, _volume_payload
from ..application import call_viewset_action
from ..errors import AgentError


class VolumeListCreateView(AgentPage):
    agent_contract_path = "/agent/v1/volumes"

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

