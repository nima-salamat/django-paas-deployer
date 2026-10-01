from rest_framework.permissions import BasePermission
class IsAgentAuthenticated(BasePermission):
    message="Agent authentication is required."
    def has_permission(self,request,view): return bool(getattr(request,"agent",None) and getattr(request.user,"is_authenticated",False))
class AgentScopePermission(BasePermission):
    def has_permission(self,request,view):
        agent=getattr(request,"agent",None)
        if agent is None:return False
        mapping=getattr(view,"required_scopes_by_method",None)
        required=set(mapping.get(request.method,()) if mapping is not None else getattr(view,"required_scopes",()) or ())
        missing=sorted(required-set(agent.scopes or []))
        if missing:
            self.message={"code":"INSUFFICIENT_SCOPE","detail":"The Agent does not have the required scope(s).","missing_scopes":missing}
            return False
        return True
