"""Wagtail viewsets for Agent control and read-only credentials."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from cms.wagtail_admin.utils import panels_for, read_only_panels
from wagtail.permission_policies.base import ModelPermissionPolicy
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from agent.models import Agent, AgentCredential, AgentAuditEvent


class ReadOnlyCredentialPolicy(ModelPermissionPolicy):
    def user_has_permission(self, user, action):
        if action in {"add", "change", "delete"}:
            return False
        return super().user_has_permission(user, action)


class AgentManagementPolicy(ModelPermissionPolicy):
    """Allow normal Wagtail edits but force deletion through Agent revocation."""

    def user_has_permission(self, user, action):
        if action == "delete":
            return False
        return super().user_has_permission(user, action)


class AgentViewSet(SnippetViewSet):
    model = Agent
    permission_policy = AgentManagementPolicy(Agent)
    icon = "user"
    menu_label = _("Agents")
    menu_order = 115
    list_display = ["name", "user", "status", "last_used_at", "created_at"]
    list_filter = ["status", "user"]
    search_fields = ["name", "description", "user__username", "user__email"]
    panels = panels_for(
        editable=["user", "name", "description", "scopes", "metadata"],
        read_only=[
            "id", "status", "last_used_at", "disabled_at", "revoked_at",
            "created_at", "updated_at",
        ],
    )


class AgentCredentialViewSet(SnippetViewSet):
    model = AgentCredential
    permission_policy = ReadOnlyCredentialPolicy(AgentCredential)
    inspect_view_enabled = True
    copy_view_enabled = False
    icon = "key"
    menu_label = _("Agent credentials")
    menu_order = 116
    list_display = [
        "agent", "token_prefix", "token_type", "expires_at",
        "revoked_at", "last_used_at", "created_at",
    ]
    list_filter = ["token_type", "revoked_at", "agent"]
    search_fields = ["token_prefix", "agent__name", "agent__user__username"]
    panels = read_only_panels([
        "id", "agent", "token_prefix", "token_type", "expires_at",
        "revoked_at", "last_used_at", "last_used_ip", "metadata",
        "created_at", "updated_at",
    ])


class AgentAuditEventViewSet(SnippetViewSet):
    model = AgentAuditEvent
    permission_policy = ReadOnlyCredentialPolicy(AgentAuditEvent)
    inspect_view_enabled = True
    copy_view_enabled = False
    icon = "history"
    menu_label = _("Agent audit events")
    menu_order = 117
    list_display = [
        "occurred_at", "agent", "action", "resource_type", "resource_id",
        "success", "http_status", "error_code", "request_id",
    ]
    list_filter = ["success", "agent", "action", "resource_type"]
    search_fields = ["action", "resource_type", "resource_id", "request_id", "error_code"]
    panels = read_only_panels([
        "id", "agent", "user", "credential", "action", "resource_type",
        "resource_id", "request_id", "occurred_at", "success", "http_status",
        "error_code", "failure_domain", "retryability", "visibility",
        "resource_effect", "certainty", "duration_ms", "metadata",
    ])


class AgentGroup(SnippetViewSetGroup):
    items = (AgentViewSet, AgentCredentialViewSet, AgentAuditEventViewSet)
    menu_label = _("Agent")
    menu_icon = "user"
    menu_order = 115
