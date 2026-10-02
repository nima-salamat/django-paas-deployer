from django.urls import path

from .user_api import (
    AgentAuditView,
    AgentCredentialListView,
    AgentCredentialRevokeView,
    AgentCredentialRotateView,
    AgentDetailView,
    AgentListCreateView,
    AgentManifestManagementView,
    AgentScopeCatalogView,
    AgentStatusView,
)

app_name = "agent_management"

urlpatterns = [
    path("scopes/", AgentScopeCatalogView.as_view(), name="scopes"),
    path("", AgentListCreateView.as_view(), name="list_create"),
    path("<uuid:agent_id>/", AgentDetailView.as_view(), name="detail"),
    path("<uuid:agent_id>/credentials/", AgentCredentialListView.as_view(), name="credentials"),
    path("<uuid:agent_id>/credentials/rotate/", AgentCredentialRotateView.as_view(), name="credentials_rotate"),
    path("<uuid:agent_id>/credentials/<uuid:credential_id>/revoke/", AgentCredentialRevokeView.as_view(), name="credential_revoke"),
    path("<uuid:agent_id>/<str:action>/", AgentStatusView.as_view(), name="status"),
    path("<uuid:agent_id>/audit/", AgentAuditView.as_view(), name="audit"),
    path("<uuid:agent_id>/manifest/", AgentManifestManagementView.as_view(), name="manifest"),
]
