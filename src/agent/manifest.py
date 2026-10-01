from django.conf import settings
from django.template.loader import render_to_string

def api_base_url(request=None):
    configured=str(getattr(settings,"AGENT_API_BASE_URL","") or "").rstrip("/")
    if configured:return configured
    if request:return f"{'https' if request.is_secure() else 'http'}://{request.get_host()}/agent/v1"
    return "/agent/v1"

def render_agent_manifest(agent,enrollment_token,*,request=None):
    from .scopes import SCOPE_LABELS
    return render_to_string("agent/AGENT.md",{"agent":agent,"agent_id":str(agent.pk),"api_base_url":api_base_url(request),"enrollment_token":enrollment_token,"scopes":[SCOPE_LABELS.get(s,s) for s in sorted(agent.scopes or [])]})
