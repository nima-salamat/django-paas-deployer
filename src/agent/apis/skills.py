from __future__ import annotations

from django.http import Http404, HttpResponse
from rest_framework.response import Response

from .base import AgentSecuredAPIView
from ..errors import AgentError
from ..skills import all_skills, skill_for_agent, skills_for_agent, skill_url
from ..manifest import api_base_url


class SkillIndexView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/skills"

    def get(self, request):
        base = api_base_url(request)
        items = []
        for skill in skills_for_agent(request.agent):
            items.append({
                "name": skill.name,
                "title": skill.title,
                "summary": skill.summary,
                "url": skill_url(base, skill),
                "required_scopes": list(skill.scopes),
                "required_any_scopes": list(skill.any_scopes),
            })
        return Response({
            "result": "success",
            "api_version": "v1",
            "skills": items,
        })


class SkillDetailView(AgentSecuredAPIView):
    agent_contract_path = "/agent/v1/skills/{skill_name}"

    def get(self, request, skill_name):
        known = next((item for item in all_skills() if item.name == str(skill_name)), None)
        if known is None:
            raise AgentError(
                "SKILL_NOT_FOUND",
                "The requested Agent skill does not exist.",
                status_code=404,
                failure_domain="resource",
            )

        skill = skill_for_agent(skill_name, request.agent)
        if skill is None:
            required = list(known.scopes)
            required_any = list(known.any_scopes)
            extra = {}
            if required:
                extra["required_scopes"] = required
            if required_any:
                extra["required_any_scopes"] = required_any
            raise AgentError(
                "INSUFFICIENT_SCOPE",
                "The Agent does not have the scope(s) required for this skill.",
                status_code=403,
                failure_domain="authorization",
                extra=extra,
            )

        base = api_base_url(request)
        body = skill.body.replace("{{base}}", base.rstrip("/"))
        body = (
            body.rstrip()
            + "\n\n---\n"
            + f"Skill endpoint: {skill_url(base, skill)}\n"
            + f"Required scopes: {', '.join(skill.scopes) if skill.scopes else 'none'}"
        )
        response = HttpResponse(body + "\n", content_type="text/markdown; charset=utf-8")
        response["Cache-Control"] = "private, no-cache"
        return response
