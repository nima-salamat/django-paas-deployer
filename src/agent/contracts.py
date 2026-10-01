"""Single source of truth for Agent API operation contracts.

The Agent facade has three consumers that must never drift:
runtime authorization, machine-readable OpenAPI, and AGENT.md bootstrap
documentation.  Route contracts live here so scopes and operational metadata
are declared once and projected into all three surfaces.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class EndpointContract:
    path: str
    method: str
    scopes: tuple[str, ...] = ()
    any_scopes: tuple[str, ...] = ()
    mutating: bool = False
    idempotent: bool = False
    throttle_scope: str = "read"
    summary_key: str = ""


def _contract(
    path: str,
    method: str,
    *,
    scopes: Iterable[str] = (),
    any_scopes: Iterable[str] = (),
    mutating: bool = False,
    idempotent: bool = False,
    throttle_scope: str = "read",
    summary_key: str = "",
) -> EndpointContract:
    return EndpointContract(
        path=path,
        method=method.upper(),
        scopes=tuple(scopes),
        any_scopes=tuple(any_scopes),
        mutating=mutating,
        idempotent=idempotent,
        throttle_scope=throttle_scope,
        summary_key=summary_key,
    )


CONTRACTS: tuple[EndpointContract, ...] = (
    _contract("/agent/v1/", "GET", scopes=("services.read",)),
    _contract("/agent/v1/auth/exchange", "POST", throttle_scope="exchange"),
    _contract("/agent/v1/auth/me", "GET"),
    _contract("/agent/v1/capabilities", "GET"),
    _contract("/agent/v1/openapi.json", "GET"),
    _contract("/agent/v1/agent.md", "GET", scopes=("agent.manifest.generate",), throttle_scope="mutation"),

    _contract("/agent/v1/services", "GET", scopes=("services.read",)),
    _contract("/agent/v1/services", "POST", scopes=("services.create",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/from-plan", "POST", scopes=("services.create", "plans.apply"), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/{service_id}", "GET", scopes=("services.read",)),
    _contract("/agent/v1/services/{service_id}", "PATCH", scopes=("services.update",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/{service_id}", "DELETE", scopes=("services.delete",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/{service_id}/start", "POST", scopes=("services.start",), mutating=True, idempotent=True, throttle_scope="deployment"),
    _contract("/agent/v1/services/{service_id}/stop", "POST", scopes=("services.stop",), mutating=True, idempotent=True, throttle_scope="deployment"),
    _contract("/agent/v1/services/{service_id}/restart", "POST", scopes=("services.restart",), mutating=True, idempotent=True, throttle_scope="deployment"),
    _contract("/agent/v1/services/{service_id}/purge-runtime", "POST", scopes=("services.purge",), mutating=True, idempotent=True, throttle_scope="deployment"),
    _contract("/agent/v1/services/{service_id}/status", "GET", scopes=("services.read",)),
    _contract("/agent/v1/services/{service_id}/logs", "GET", scopes=("service_logs.read",)),
    _contract("/agent/v1/services/{service_id}/logs/export", "GET", scopes=("service_logs.export",)),
    _contract("/agent/v1/services/{service_id}/configuration", "GET", scopes=("service_config.read",)),
    _contract("/agent/v1/services/{service_id}/configuration", "PATCH", scopes=("service_config.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/{service_id}/environment", "GET", scopes=("service_environment.read",)),
    _contract("/agent/v1/services/{service_id}/environment", "POST", scopes=("service_environment.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/{service_id}/environment", "DELETE", scopes=("service_environment.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/{service_id}/secrets", "GET", scopes=("service_secrets.read",)),
    _contract("/agent/v1/services/{service_id}/secrets", "POST", scopes=("service_secrets.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/{service_id}/secrets", "DELETE", scopes=("service_secrets.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/{service_id}/endpoints", "GET", scopes=("service_endpoints.read",)),
    _contract("/agent/v1/services/{service_id}/endpoints", "POST", scopes=("service_endpoints.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/{service_id}/endpoints", "DELETE", scopes=("service_endpoints.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/{service_id}/networks", "GET", scopes=("service_networks.read",)),
    _contract("/agent/v1/services/{service_id}/networks", "POST", scopes=("service_networks.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/{service_id}/networks", "DELETE", scopes=("service_networks.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/{service_id}/databases", "GET", scopes=("service_config.read",)),
    _contract("/agent/v1/services/{service_id}/databases", "POST", scopes=("service_config.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/{service_id}/databases", "DELETE", scopes=("service_config.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/services/{service_id}/revisions", "GET", scopes=("services.read",)),
    _contract("/agent/v1/services/{service_id}/revisions/{revision_id}", "GET", scopes=("services.read",)),
    _contract("/agent/v1/services/{service_id}/revisions/{revision_id}/rollback", "POST", scopes=("deployments.rollback",), mutating=True, idempotent=True, throttle_scope="deployment"),

    _contract("/agent/v1/services/{service_id}/shell", "GET", scopes=("shell.read",), throttle_scope="shell"),
    _contract("/agent/v1/services/{service_id}/shell/sessions", "POST", scopes=("shell.read", "shell.execute"), mutating=True, throttle_scope="shell"),
    _contract("/agent/v1/services/{service_id}/shell/sessions/{session_id}/commands", "POST", scopes=("shell.execute",), mutating=True, throttle_scope="shell"),
    _contract("/agent/v1/services/{service_id}/shell/sessions/{session_id}/close", "POST", scopes=("shell.execute",), mutating=True, throttle_scope="shell"),
    _contract("/agent/v1/services/{service_id}/shell/replace", "POST", scopes=("shell.replace",), mutating=True, throttle_scope="shell"),
    _contract("/agent/v1/services/{service_id}/shell/files", "POST", any_scopes=("shell.files.read", "shell.files.write"), mutating=True, throttle_scope="shell"),

    _contract("/agent/v1/plans", "GET", scopes=("plans.read",)),
    _contract("/agent/v1/plans/{plan_id}", "GET", scopes=("plans.read",)),
    _contract("/agent/v1/plans/{plan_id}/apply", "POST", scopes=("plans.apply", "services.create"), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/plans/manage", "POST", scopes=("plans.manage",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/plans/manage/{plan_id}", "PATCH", scopes=("plans.manage",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/plans/manage/{plan_id}", "DELETE", scopes=("plans.manage",), mutating=True, idempotent=True, throttle_scope="mutation"),

    _contract("/agent/v1/networks", "GET", scopes=("service_networks.read",)),
    _contract("/agent/v1/networks", "POST", scopes=("service_networks.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/networks/{network_id}", "GET", scopes=("service_networks.read",)),
    _contract("/agent/v1/networks/{network_id}", "PATCH", scopes=("service_networks.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/networks/{network_id}", "DELETE", scopes=("service_networks.write",), mutating=True, idempotent=True, throttle_scope="mutation"),

    _contract("/agent/v1/volumes", "GET", scopes=("service_volumes.read",)),
    _contract("/agent/v1/volumes", "POST", scopes=("service_volumes.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/volumes/{volume_id}", "GET", scopes=("service_volumes.read",)),
    _contract("/agent/v1/volumes/{volume_id}", "PATCH", scopes=("service_volumes.write",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/volumes/{volume_id}", "DELETE", scopes=("service_volumes.write",), mutating=True, idempotent=True, throttle_scope="mutation"),

    _contract("/agent/v1/deployments", "GET", scopes=("deployments.read",)),
    _contract("/agent/v1/deployments", "POST", scopes=("deployments.create",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/deployments/{deployment_id}", "GET", scopes=("deployments.read",)),
    _contract("/agent/v1/deployments/{deployment_id}", "DELETE", scopes=("deployments.delete",), mutating=True, idempotent=True, throttle_scope="mutation"),
    _contract("/agent/v1/deployments/{deployment_id}/upload", "POST", scopes=("deployments.upload",), mutating=True, idempotent=True, throttle_scope="upload"),
    _contract("/agent/v1/deployments/{deployment_id}/start", "POST", scopes=("deployments.start",), mutating=True, idempotent=True, throttle_scope="deployment"),
    _contract("/agent/v1/deployments/{deployment_id}/cancel", "POST", scopes=("deployments.cancel",), mutating=True, idempotent=True, throttle_scope="deployment"),
    _contract("/agent/v1/deployments/{deployment_id}/redeploy", "POST", scopes=("deployments.redeploy",), mutating=True, idempotent=True, throttle_scope="deployment"),
    _contract("/agent/v1/deployments/{deployment_id}/rebuild", "POST", scopes=("deployments.rebuild",), mutating=True, idempotent=True, throttle_scope="deployment"),
    _contract("/agent/v1/deployments/{deployment_id}/rollback", "POST", scopes=("deployments.rollback",), mutating=True, idempotent=True, throttle_scope="deployment"),
    _contract("/agent/v1/deployments/{deployment_id}/logs", "GET", scopes=("deployments.logs.read",)),
    _contract("/agent/v1/deployments/{deployment_id}/logs/export", "GET", scopes=("deployments.logs.export",)),
)


_INDEX = {(item.path, item.method): item for item in CONTRACTS}


def contract_for(path: str, method: str) -> EndpointContract | None:
    """Return the exact contract for a canonical Agent route."""
    return _INDEX.get((str(path), str(method).upper()))


def required_scopes_for(path: str, method: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    contract = contract_for(path, method)
    if contract is None:
        return (), ()
    return contract.scopes, contract.any_scopes


def contracts_for_agent(agent) -> list[EndpointContract]:
    """Return the operations this Agent can actually invoke."""
    selected = set(agent.scopes or [])
    result = []
    for contract in CONTRACTS:
        if set(contract.scopes).issubset(selected) and (
            not contract.any_scopes or bool(set(contract.any_scopes) & selected)
        ):
            result.append(contract)
    return result
