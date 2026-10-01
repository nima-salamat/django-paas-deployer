"""Staff-only Wagtail actions for Agent credential lifecycle."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .application import audit, create_enrollment, issue_access_credential
from .manifest import render_agent_manifest
from .models import Agent, AgentCredential


def can_manage(user):
    return bool(
        getattr(user, "is_staff", False)
        and (
            getattr(user, "is_superuser", False)
            or user.has_perm("agent.change_agent")
        )
    )


def _return_agent(request, agent):
    try:
        return redirect("wagtailsnippets_agent_agent:list")
    except Exception:
        return redirect("/admin/snippets/")


def _confirm_page(request, title, action_url, description, method="POST"):
    safe_title = title.replace("<", "&lt;").replace(">", "&gt;")
    body = description.replace("<", "&lt;").replace(">", "&gt;")
    return HttpResponse(
        f"""<!doctype html><html><body>
<h1>{safe_title}</h1><p>{body}</p>
<form method="{method}" action="{action_url}">
<input type="hidden" name="csrfmiddlewaretoken" value="{get_token(request)}">
<button type="submit">Confirm</button>
</form>
</body></html>""",
        content_type="text/html; charset=utf-8",
    )


@staff_member_required
@require_GET
def issue_credential_confirm(request, agent_id):
    if not can_manage(request.user):
        return HttpResponse("Forbidden", status=403)
    agent = get_object_or_404(Agent, pk=agent_id)
    return _confirm_page(
        request,
        "Issue Agent credential",
        reverse("wagtail_agent_issue_credential", kwargs={"agent_id": agent.pk}),
        f"Issue a new expiring Bearer credential for Agent {agent.name}. The plaintext will be shown once.",
    )


@staff_member_required
@require_POST
def issue_credential(request, agent_id):
    if not can_manage(request.user):
        return HttpResponse("Forbidden", status=403)
    agent = get_object_or_404(Agent, pk=agent_id)
    if agent.status != Agent.Status.ACTIVE:
        return HttpResponse("Agent is not active.", status=409)
    credential, token = issue_access_credential(
        agent,
        metadata={"issued_by_wagtail_user": str(request.user.pk)},
    )
    audit(
        request=request, agent=agent, user=request.user, credential=credential,
        action="admin.credential.issue", success=True, status_code=201,
        resource_type="agent_credential", resource_id=credential.pk,
        resource_effect="changed",
    )
    return HttpResponse(
        f"""<!doctype html><html><body>
<h1>Agent credential issued</h1>
<p>This credential is shown once. Store it in the external Agent secret store.</p>
<pre>{token}</pre>
<p>Credential ID: {credential.pk}</p>
<p>Expires: {credential.expires_at}</p>
</body></html>""",
        content_type="text/html; charset=utf-8",
    )


@staff_member_required
@require_GET
def rotate_credential_confirm(request, agent_id):
    if not can_manage(request.user):
        return HttpResponse("Forbidden", status=403)
    agent = get_object_or_404(Agent, pk=agent_id)
    return _confirm_page(
        request,
        "Rotate Agent credentials",
        reverse("wagtail_agent_rotate_credential", kwargs={"agent_id": agent.pk}),
        f"Revoke all currently-active credentials and issue one new credential for Agent {agent.name}.",
    )


@staff_member_required
@require_POST
def rotate_credential(request, agent_id):
    if not can_manage(request.user):
        return HttpResponse("Forbidden", status=403)
    agent = get_object_or_404(Agent, pk=agent_id)
    if agent.status != Agent.Status.ACTIVE:
        return HttpResponse("Agent is not active.", status=409)
    now = timezone.now()
    AgentCredential.objects.filter(agent=agent, revoked_at__isnull=True).update(
        revoked_at=now, updated_at=now
    )
    credential, token = issue_access_credential(
        agent,
        metadata={"rotated_by_wagtail_user": str(request.user.pk)},
    )
    audit(
        request=request, agent=agent, user=request.user, credential=credential,
        action="admin.credential.rotate", success=True, status_code=201,
        resource_type="agent", resource_id=agent.pk, resource_effect="changed",
        metadata={"revoked_previous_credentials": True},
    )
    return HttpResponse(
        f"""<!doctype html><html><body>
<h1>Agent credential rotated</h1>
<p>All previous active Agent credentials were revoked.</p>
<p>The new Bearer credential is shown once:</p>
<pre>{token}</pre>
<p>Expires: {credential.expires_at}</p>
</body></html>""",
        content_type="text/html; charset=utf-8",
    )


@staff_member_required
@require_GET
def revoke_credential_confirm(request, credential_id):
    if not can_manage(request.user):
        return HttpResponse("Forbidden", status=403)
    credential = get_object_or_404(AgentCredential, pk=credential_id)
    return _confirm_page(
        request,
        "Revoke Agent credential",
        reverse("wagtail_agent_revoke_credential", kwargs={"credential_id": credential.pk}),
        f"Revoke credential {credential.token_prefix}? It cannot be reactivated.",
    )


@staff_member_required
@require_POST
def revoke_credential(request, credential_id):
    if not can_manage(request.user):
        return HttpResponse("Forbidden", status=403)
    credential = get_object_or_404(AgentCredential, pk=credential_id)
    if credential.revoked_at is None:
        credential.revoked_at = timezone.now()
        credential.save(update_fields=["revoked_at", "updated_at"])
    audit(
        request=request, agent=credential.agent, user=request.user, credential=credential,
        action="admin.credential.revoke", success=True, status_code=200,
        resource_type="agent_credential", resource_id=credential.pk,
        resource_effect="changed",
    )
    messages.success(request, "Agent credential revoked.")
    return _return_agent(request, credential.agent)


@staff_member_required
@require_GET
def disable_agent_confirm(request, agent_id):
    if not can_manage(request.user):
        return HttpResponse("Forbidden", status=403)
    agent = get_object_or_404(Agent, pk=agent_id)
    return _confirm_page(
        request,
        "Disable Agent",
        reverse("wagtail_agent_disable", kwargs={"agent_id": agent.pk}),
        f"Disable Agent {agent.name}? All authentication attempts will stop working until it is re-enabled.",
    )


@staff_member_required
@require_POST
def disable_agent(request, agent_id):
    if not can_manage(request.user):
        return HttpResponse("Forbidden", status=403)
    agent = get_object_or_404(Agent, pk=agent_id)
    now = timezone.now()
    agent.status = Agent.Status.DISABLED
    agent.disabled_at = now
    agent.save(update_fields=["status", "disabled_at", "updated_at"])
    AgentCredential.objects.filter(agent=agent, revoked_at__isnull=True).update(
        revoked_at=now, updated_at=now
    )
    audit(
        request=request, agent=agent, user=request.user,
        action="admin.agent.disable", success=True, status_code=200,
        resource_type="agent", resource_id=agent.pk, resource_effect="changed",
    )
    messages.success(request, "Agent disabled and active credentials revoked.")
    return _return_agent(request, agent)


@staff_member_required
@require_GET
def revoke_agent_confirm(request, agent_id):
    if not can_manage(request.user):
        return HttpResponse("Forbidden", status=403)
    agent = get_object_or_404(Agent, pk=agent_id)
    return _confirm_page(
        request,
        "Revoke Agent",
        reverse("wagtail_agent_revoke", kwargs={"agent_id": agent.pk}),
        f"Revoke Agent {agent.name}? This is intended to be permanent.",
    )


@staff_member_required
@require_POST
def revoke_agent(request, agent_id):
    if not can_manage(request.user):
        return HttpResponse("Forbidden", status=403)
    agent = get_object_or_404(Agent, pk=agent_id)
    now = timezone.now()
    agent.status = Agent.Status.REVOKED
    agent.revoked_at = now
    agent.save(update_fields=["status", "revoked_at", "updated_at"])
    AgentCredential.objects.filter(agent=agent, revoked_at__isnull=True).update(
        revoked_at=now, updated_at=now
    )
    audit(
        request=request, agent=agent, user=request.user,
        action="admin.agent.revoke", success=True, status_code=200,
        resource_type="agent", resource_id=agent.pk, resource_effect="changed",
    )
    messages.success(request, "Agent revoked and active credentials invalidated.")
    return _return_agent(request, agent)


@staff_member_required
@require_GET
def manifest(request, agent_id):
    if not can_manage(request.user):
        return HttpResponse("Forbidden", status=403)
    agent = get_object_or_404(Agent, pk=agent_id)
    if agent.status != Agent.Status.ACTIVE:
        return HttpResponse("Agent is not active.", status=409)
    enrollment, row = create_enrollment(agent, request=request)
    content = render_agent_manifest(agent, enrollment, request=request)
    audit(
        request=request, agent=agent, user=request.user,
        action="admin.agent_manifest.generate", success=True, status_code=200,
        resource_type="agent", resource_id=agent.pk, resource_effect="unchanged",
        metadata={"enrollment_prefix": row.token_prefix, "enrollment_expires_at": row.expires_at.isoformat()},
    )
    return HttpResponse(
        content,
        content_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="AGENT-{agent.pk}.md"'},
    )
