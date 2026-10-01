from __future__ import annotations

from rest_framework.response import Response
from .base import AgentSecuredAPIView, AgentPage, idempotent
from .helpers import _NetworkSerializer, _network_payload
from ..application import call_viewset_action
from ..errors import AgentError


class NetworkListCreateView(AgentPage):
    agent_contract_path = "/agent/v1/networks"

    audit_resource_type="network"
    def get(self,request):
        from ..application import network_queryset
        self.audit_action="networks.list"; return self.paginate(request,network_queryset(request.user),_NetworkSerializer)
    @idempotent
    def post(self,request):
        from ..application import create_network,network_payload
        network=create_network(request,dict(request.data)); self.audit_action="networks.create"; self.audit_mutating=True
        return Response({"result":"success","network":network_payload(network)},status=201)

class NetworkDetailView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/networks/{network_id}"

    audit_resource_type="network"
    def get(self,request,network_id):
        from ..application import network_queryset,network_payload
        network=network_queryset(request.user).filter(pk=network_id).first()
        if not network:raise AgentError("NETWORK_NOT_FOUND","Network not found.",status_code=404,failure_domain="resource")
        self.audit_action="networks.retrieve"; return Response({"result":"success","network":network_payload(network)})
    @idempotent
    def patch(self,request,network_id):
        from ..application import network_queryset,update_network,network_payload
        network=network_queryset(request.user).filter(pk=network_id).first()
        if not network:raise AgentError("NETWORK_NOT_FOUND","Network not found.",status_code=404)
        network=update_network(request,network.pk,dict(request.data))
        if isinstance(network, Response):
            return network
        self.audit_action="networks.update"; self.audit_mutating=True
        return Response({"result":"success","network":network_payload(network)})
    @idempotent
    def delete(self,request,network_id):
        from ..application import network_queryset
        from services.api.user_services import PrivateNetworkViewSet
        network=network_queryset(request.user).filter(pk=network_id).first()
        if not network:raise AgentError("NETWORK_NOT_FOUND","Network not found.",status_code=404)
        response=call_viewset_action(PrivateNetworkViewSet,"destroy",request,pk=network.pk)
        self.audit_action="networks.delete"; self.audit_mutating=True; return response

