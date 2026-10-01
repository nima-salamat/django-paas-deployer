from rest_framework.permissions import BasePermission

from .errors import AgentError
from .contracts import contract_for


def _contract_path(view, request):
    resolver = getattr(view, "get_agent_contract_path", None)
    if callable(resolver):
        return resolver(request)
    return getattr(view, "agent_contract_path", None)


def _required_scopes(view, request):
    path = _contract_path(view, request)
    if path:
        contract = contract_for(path, request.method)
        if contract is not None:
            return contract.scopes, contract.any_scopes
    mapping = getattr(view, "required_scopes_by_method", None)
    if mapping:
        method = request.method.upper()
        if method == "HEAD" and "GET" in mapping:
            method = "GET"
        return tuple(mapping.get(method, ())), ()
    return tuple(getattr(view, "required_scopes", ()) or ()), ()


class IsAgentAuthenticated(BasePermission):
    message = "Agent authentication is required."

    def has_permission(self, request, view):
        return bool(
            getattr(request, "agent", None)
            and getattr(request.user, "is_authenticated", False)
        )


class AgentScopePermission(BasePermission):
    """Enforce the centralized Agent contract while preserving User auth."""

    def has_permission(self, request, view):
        agent = getattr(request, "agent", None)
        if agent is None:
            return False

        required, any_required = _required_scopes(view, request)
        selected = set(agent.scopes or [])
        missing = sorted(set(required) - selected)
        if missing:
            raise AgentError(
                "INSUFFICIENT_SCOPE",
                "The Agent does not have the required scope(s).",
                status_code=403,
                failure_domain="authorization",
                extra={"missing_scopes": missing},
            )

        if any_required and not (set(any_required) & selected):
            raise AgentError(
                "INSUFFICIENT_SCOPE",
                "The Agent does not have any scope required for this operation.",
                status_code=403,
                failure_domain="authorization",
                extra={"required_any_scopes": sorted(any_required)},
            )
        return True
