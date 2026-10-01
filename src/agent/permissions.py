from rest_framework.permissions import BasePermission

from .errors import AgentError


class IsAgentAuthenticated(BasePermission):
    message = "Agent authentication is required."

    def has_permission(self, request, view):
        return bool(
            getattr(request, "agent", None)
            and getattr(request.user, "is_authenticated", False)
        )


class AgentScopePermission(BasePermission):
    """Require Agent scopes without replacing the underlying User authorization."""

    def has_permission(self, request, view):
        agent = getattr(request, "agent", None)
        if agent is None:
            return False

        mapping = getattr(view, "required_scopes_by_method", None)
        if mapping:
            method = request.method.upper()
            if method == "HEAD" and "GET" in mapping:
                method = "GET"
            required = set(mapping.get(method, ()))
        else:
            required = set(getattr(view, "required_scopes", ()) or ())

        missing = sorted(required - set(agent.scopes or []))
        if missing:
            raise AgentError(
                "INSUFFICIENT_SCOPE",
                "The Agent does not have the required scope(s).",
                status_code=403,
                failure_domain="authorization",
                extra={"missing_scopes": missing},
            )
        return True
