from django.conf import settings
from django.template.loader import render_to_string

def api_base_url(request=None):
    configured=str(getattr(settings,"AGENT_API_BASE_URL","") or "").rstrip("/")
    if configured:return configured
    if request:return f"{'https' if request.is_secure() else 'http'}://{request.get_host()}/agent/v1"
    return "/agent/v1"

def render_agent_manifest(agent,enrollment_token,*,request=None):
    selected = set(agent.scopes or [])
    capabilities = {
        "services": {key: scope in selected for key, scope in {
            "read": "services.read", "create": "services.create", "update": "services.update",
            "delete": "services.delete", "start": "services.start", "stop": "services.stop",
            "restart": "services.restart", "purge": "services.purge",
        }.items()},
        "plans": {"read": "plans.read" in selected, "apply": "plans.apply" in selected and "services.create" in selected, "manage": "plans.manage" in selected},
        "networks": {"read": "service_networks.read" in selected, "write": "service_networks.write" in selected},
        "volumes": {"read": "service_volumes.read" in selected, "write": "service_volumes.write" in selected},
        "deployments": {key: scope in selected for key, scope in {
            "read": "deployments.read", "create": "deployments.create", "upload": "deployments.upload",
            "start": "deployments.start", "cancel": "deployments.cancel", "redeploy": "deployments.redeploy",
            "rebuild": "deployments.rebuild", "rollback": "deployments.rollback", "delete": "deployments.delete",
            "logs_read": "deployments.logs.read", "logs_export": "deployments.logs.export",
        }.items()},
        "config": {"read": "service_config.read" in selected, "write": "service_config.write" in selected},
        "environment": {"read": "service_environment.read" in selected, "write": "service_environment.write" in selected},
        "secrets": {"read": "service_secrets.read" in selected, "write": "service_secrets.write" in selected},
        "endpoints": {"read": "service_endpoints.read" in selected, "write": "service_endpoints.write" in selected},
        "service_networks": {"read": "service_networks.read" in selected, "write": "service_networks.write" in selected},
        "shell": {
            "read": "shell.read" in selected, "execute": "shell.execute" in selected,
            "replace": "shell.replace" in selected, "files_read": "shell.files.read" in selected,
            "files_write": "shell.files.write" in selected,
        },
        "manifest": "agent.manifest.generate" in selected,
        "runtime_logs": {"read": "service_logs.read" in selected, "export": "service_logs.export" in selected},
    }
    return render_to_string(
        "agent/AGENT.md",
        {
            "agent": agent,
            "agent_id": str(agent.pk),
            "api_base_url": api_base_url(request),
            "enrollment_token": enrollment_token,
            "scopes": sorted(selected),
            "capabilities": capabilities,
        },
    )
