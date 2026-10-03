from django.conf import settings
from django.template.loader import render_to_string

from .contracts import contracts_for_agent
from .skills import skills_for_agent, skill_url


def api_base_url(request=None):
    configured = str(getattr(settings, "AGENT_API_BASE_URL", "") or "").rstrip("/")
    if configured:
        return configured
    if request:
        return f"{'https' if request.is_secure() else 'http'}://{request.get_host()}/agent/v1"
    return "/agent/v1"


def manifest_endpoints(agent):
    endpoints = []
    for contract in contracts_for_agent(agent):
        requirement = []
        if contract.scopes:
            requirement.append("all: " + ", ".join(contract.scopes))
        if contract.any_scopes:
            requirement.append("any: " + ", ".join(contract.any_scopes))
        endpoints.append(
            {
                "method": contract.method,
                "path": contract.path,
                "requirements": " + ".join(requirement) if requirement else "none",
                "mutating": contract.mutating,
                "idempotent": contract.idempotent,
                "throttle": contract.throttle_scope,
            }
        )
    return endpoints


def manifest_skills(agent, request=None):
    base = api_base_url(request)
    return [
        {
            "name": skill.name,
            "title": skill.title,
            "summary": skill.summary,
            "url": skill_url(base, skill),
            "required_scopes": list(skill.scopes),
            "required_any_scopes": list(skill.any_scopes),
        }
        for skill in skills_for_agent(agent)
    ]


def render_agent_manifest(agent, enrollment_token=None, *, access_token=None, request=None):
    selected = set(agent.scopes or [])
    return render_to_string(
        "agent/AGENT.md",
        {
            "agent": agent,
            "agent_id": str(agent.pk),
            "api_base_url": api_base_url(request),
            "enrollment_token": enrollment_token,
            "access_token": access_token,
            "scopes": sorted(selected),
            "endpoints": manifest_endpoints(agent),
            "skills": manifest_skills(agent, request),
        },
    )
