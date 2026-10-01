"""Wagtail hooks for Agent administration."""
from __future__ import annotations

from django.urls import path, reverse
from django.utils.http import urlencode
from wagtail import hooks
from wagtail.snippets import widgets as wagtailsnippets_widgets

from .wagtail_admin import register as _register_agent

from .admin_actions import (
    disable_agent,
    disable_agent_confirm,
    enable_agent,
    enable_agent_confirm,
    issue_credential,
    issue_credential_confirm,
    manifest,
    manifest_confirm,
    revoke_agent,
    revoke_agent_confirm,
    revoke_credential,
    revoke_credential_confirm,
    rotate_credential,
    rotate_credential_confirm,
)
from .wagtail_admin.models import AgentGroup
from .models import Agent, AgentCredential

_register_agent()


@hooks.register("register_admin_urls")
def register_agent_admin_urls():
    return [
        path("agent/<uuid:agent_id>/issue-credential/confirm/", issue_credential_confirm, name="wagtail_agent_issue_credential_confirm"),
        path("agent/<uuid:agent_id>/issue-credential/", issue_credential, name="wagtail_agent_issue_credential"),
        path("agent/<uuid:agent_id>/rotate-credential/confirm/", rotate_credential_confirm, name="wagtail_agent_rotate_credential_confirm"),
        path("agent/<uuid:agent_id>/rotate-credential/", rotate_credential, name="wagtail_agent_rotate_credential"),
        path("agent/<uuid:agent_id>/disable/confirm/", disable_agent_confirm, name="wagtail_agent_disable_confirm"),
        path("agent/<uuid:agent_id>/disable/", disable_agent, name="wagtail_agent_disable"),
        path("agent/<uuid:agent_id>/enable/confirm/", enable_agent_confirm, name="wagtail_agent_enable_confirm"),
        path("agent/<uuid:agent_id>/enable/", enable_agent, name="wagtail_agent_enable"),
        path("agent/<uuid:agent_id>/revoke/confirm/", revoke_agent_confirm, name="wagtail_agent_revoke_confirm"),
        path("agent/<uuid:agent_id>/revoke/", revoke_agent, name="wagtail_agent_revoke"),
        path("agent/<uuid:agent_id>/agent-md/confirm/", manifest_confirm, name="wagtail_agent_manifest_confirm"),
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
    next_url = None
    try:
        next_url = context.get("next_url") if context else None
    except AttributeError:
        pass
    query = urlencode({"next": next_url}) if next_url else ""
    suffix = f"?{query}" if query else ""
    if isinstance(snippet, Agent) and snippet.status == Agent.Status.ACTIVE:
        for label, route, priority in (
            ("Issue credential", "wagtail_agent_issue_credential_confirm", 10),
            ("Rotate credentials", "wagtail_agent_rotate_credential_confirm", 20),
            ("Generate AGENT.md", "wagtail_agent_manifest_confirm", 30),
            ("Disable", "wagtail_agent_disable_confirm", 40),
            ("Revoke", "wagtail_agent_revoke_confirm", 50),
        ):
            buttons.append(wagtailsnippets_widgets.SnippetListingButton(
                label, reverse(route, kwargs={"agent_id": snippet.pk}) + suffix, priority=priority
            ))
    elif isinstance(snippet, Agent) and snippet.status == Agent.Status.DISABLED:
        buttons.append(wagtailsnippets_widgets.SnippetListingButton(
            "Enable",
            reverse("wagtail_agent_enable_confirm", kwargs={"agent_id": snippet.pk}) + suffix,
            priority=10,
        ))
    elif isinstance(snippet, AgentCredential) and snippet.revoked_at is None:
        buttons.append(wagtailsnippets_widgets.SnippetListingButton(
            "Revoke credential",
            reverse("wagtail_agent_revoke_credential_confirm", kwargs={"credential_id": snippet.pk}) + suffix,
            priority=10,
        ))
