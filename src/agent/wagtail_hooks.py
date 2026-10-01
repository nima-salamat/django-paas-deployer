"""Wagtail hooks for Agent administration."""
from __future__ import annotations

from django.urls import path, reverse
from wagtail import hooks
from wagtail.snippets.models import register_snippet

from .admin_actions import (
    disable_agent,
    disable_agent_confirm,
    issue_credential,
    issue_credential_confirm,
    manifest,
    revoke_agent,
    revoke_agent_confirm,
    revoke_credential,
    revoke_credential_confirm,
    rotate_credential,
    rotate_credential_confirm,
)
from .wagtail_admin.models import AgentGroup
from .models import Agent, AgentCredential

register_snippet(AgentGroup)


@hooks.register("register_admin_urls")
def register_agent_admin_urls():
    return [
        path("agent/<uuid:agent_id>/issue-credential/confirm/", issue_credential_confirm, name="wagtail_agent_issue_credential_confirm"),
        path("agent/<uuid:agent_id>/issue-credential/", issue_credential, name="wagtail_agent_issue_credential"),
        path("agent/<uuid:agent_id>/rotate-credential/confirm/", rotate_credential_confirm, name="wagtail_agent_rotate_credential_confirm"),
        path("agent/<uuid:agent_id>/rotate-credential/", rotate_credential, name="wagtail_agent_rotate_credential"),
        path("agent/<uuid:agent_id>/disable/confirm/", disable_agent_confirm, name="wagtail_agent_disable_confirm"),
        path("agent/<uuid:agent_id>/disable/", disable_agent, name="wagtail_agent_disable"),
        path("agent/<uuid:agent_id>/revoke/confirm/", revoke_agent_confirm, name="wagtail_agent_revoke_confirm"),
        path("agent/<uuid:agent_id>/revoke/", revoke_agent, name="wagtail_agent_revoke"),
        path("agent/<uuid:agent_id>/agent-md/", manifest, name="wagtail_agent_manifest"),
        path("agent/credentials/<uuid:credential_id>/revoke/confirm/", revoke_credential_confirm, name="wagtail_agent_revoke_credential_confirm"),
        path("agent/credentials/<uuid:credential_id>/revoke/", revoke_credential, name="wagtail_agent_revoke_credential"),
    ]


@hooks.register("construct_snippet_listing_buttons")
def agent_listing_buttons(buttons, snippet, user, context=None):
    if not getattr(user, "is_staff", False):
        return
    if not (getattr(user, "is_superuser", False) or user.has_perm("agent.change_agent")):
        return
    if isinstance(snippet, Agent):
        if snippet.status == Agent.Status.ACTIVE:
            buttons.append({
                "label": "Issue credential",
                "url": reverse("wagtail_agent_issue_credential_confirm", kwargs={"agent_id": snippet.pk}),
            })
            buttons.append({
                "label": "Rotate credentials",
                "url": reverse("wagtail_agent_rotate_credential_confirm", kwargs={"agent_id": snippet.pk}),
            })
            buttons.append({
                "label": "Generate AGENT.md",
                "url": reverse("wagtail_agent_manifest", kwargs={"agent_id": snippet.pk}),
            })
            buttons.append({
                "label": "Disable",
                "url": reverse("wagtail_agent_disable_confirm", kwargs={"agent_id": snippet.pk}),
            })
            buttons.append({
                "label": "Revoke",
                "url": reverse("wagtail_agent_revoke_confirm", kwargs={"agent_id": snippet.pk}),
            })
    elif isinstance(snippet, AgentCredential) and snippet.revoked_at is None:
        buttons.append({
            "label": "Revoke credential",
            "url": reverse("wagtail_agent_revoke_credential_confirm", kwargs={"credential_id": snippet.pk}),
        })
