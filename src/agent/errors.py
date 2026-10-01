from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed,NotAuthenticated,PermissionDenied,ValidationError
from rest_framework.response import Response
from .security import sanitize_metadata
class AgentError(Exception):
    def __init__(self,code,detail,*,status_code=400,failure_domain="request",retryability=False,visibility="client",resource_effect="unchanged",certainty="known",extra=None):
        super().__init__(detail); self.code=code; self.detail=detail; self.status_code=status_code; self.failure_domain=failure_domain; self.retryability=retryability; self.visibility=visibility; self.resource_effect=resource_effect; self.certainty=certainty; self.extra=extra or {}
def agent_error_response(exc):
    body={"result":"error","code":exc.code,"detail":exc.detail,"request_id":None,"retryable":exc.retryability,"failure_domain":exc.failure_domain,"visibility":exc.visibility,"resource_effect":exc.resource_effect,"certainty":exc.certainty}; body.update(sanitize_metadata(exc.extra)); return Response(body,status=exc.status_code)
def normalize_exception(exc,response):
    status_code=int(getattr(response,"status_code",500) or 500); raw=getattr(response,"data",None); code="INTERNAL_ERROR"; domain="runtime"; retry=False; detail=(str(exc) or "An unexpected error occurred.") if status_code < 500 else "An unexpected server error occurred."
    if isinstance(exc,(AuthenticationFailed,NotAuthenticated)) or status_code==401: code="AUTHENTICATION_REQUIRED"; domain="authentication"; status_code=401
    elif isinstance(exc,PermissionDenied) or status_code==403: code="PERMISSION_DENIED"; domain="authorization"; status_code=403
    elif isinstance(exc,(ValidationError,ValueError)) or status_code==400: code="INVALID_REQUEST"; domain="request"; status_code=400
    elif isinstance(exc,Http404) or status_code==404: code="RESOURCE_NOT_FOUND"; domain="resource"; status_code=404
    elif status_code==409: code="CONFLICT"; domain="resource"
    elif status_code==429: code="RATE_LIMITED"; domain="infrastructure"; retry=True
    if isinstance(raw,dict):
        code=str(raw.get("code") or code); detail=str(raw.get("detail") or raw.get("error") or detail) if status_code < 500 else "An unexpected server error occurred."
    elif isinstance(raw,str): detail=raw
    response.data={"result":"error","code":code,"detail":detail,"request_id":None,"retryable":retry,"failure_domain":domain,"visibility":"client","resource_effect":"unchanged","certainty":"known"}; return response
