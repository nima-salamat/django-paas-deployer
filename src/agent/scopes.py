from __future__ import annotations

from collections import OrderedDict

SERVICE_SCOPES=("services.read","services.create","services.update","services.delete","services.start","services.stop","services.restart","services.purge")
PLAN_SCOPES=("plans.read","plans.manage","plans.apply")
DEPLOYMENT_SCOPES=("deployments.read","deployments.create","deployments.upload","deployments.start","deployments.cancel","deployments.redeploy","deployments.rebuild","deployments.rollback","deployments.delete","deployments.logs.read","deployments.logs.export")
RUNTIME_SCOPES=("service_logs.read","service_logs.export")
CONFIG_SCOPES=("service_config.read","service_config.write","service_environment.read","service_environment.write","service_secrets.read","service_secrets.write","service_endpoints.read","service_endpoints.write","service_volumes.read","service_volumes.write","service_networks.read","service_networks.write")
AGENT_SCOPES=("agent.manifest.generate",)
SHELL_SCOPES=("shell.read","shell.execute","shell.replace","shell.files.read","shell.files.write")
ALL_SCOPES=frozenset(SERVICE_SCOPES+PLAN_SCOPES+DEPLOYMENT_SCOPES+RUNTIME_SCOPES+CONFIG_SCOPES+SHELL_SCOPES+AGENT_SCOPES)
DEFAULT_SCOPES=frozenset({"services.read","plans.read","deployments.read","deployments.logs.read","service_logs.read","service_config.read","service_environment.read","service_endpoints.read","service_volumes.read","service_networks.read"})
SCOPE_LABELS=OrderedDict((s,s.replace("."," / ").replace("_"," ").capitalize()) for s in sorted(ALL_SCOPES))
DESTRUCTIVE_SCOPES=frozenset({
    "services.delete","services.purge","deployments.cancel","deployments.delete",
    "deployments.rollback","shell.execute","shell.replace","shell.files.write",
    "service_secrets.write","service_volumes.write","service_networks.write",
})

HIGH_RISK_SCOPES=frozenset({"agent.manifest.generate","services.delete","services.purge","deployments.cancel","deployments.rebuild","deployments.rollback","deployments.delete","service_secrets.write","service_volumes.write","service_networks.write","shell.execute","shell.replace","shell.files.write"})

def validate_scopes(scopes):
    values=sorted({str(s).strip() for s in (scopes or []) if str(s).strip()})
    unknown=[s for s in values if s not in ALL_SCOPES]
    if unknown:
        raise ValueError(f"Unknown Agent scopes: {', '.join(unknown)}")
    return values

def scope_categories(scopes):
    selected=set(scopes or [])
    return {name:[s for s in group if s in selected] for name,group in {
        "services":SERVICE_SCOPES,"plans":PLAN_SCOPES,"deployments":DEPLOYMENT_SCOPES,
        "runtime_logs":RUNTIME_SCOPES,"configuration":CONFIG_SCOPES,"shell":SHELL_SCOPES,"agent":AGENT_SCOPES}.items()}


def default_agent_scopes():
    return sorted(DEFAULT_SCOPES)
