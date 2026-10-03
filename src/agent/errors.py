from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied, ValidationError
from rest_framework.response import Response
from .security import sanitize_metadata


class AgentError(Exception):
    def __init__(self, code, detail, *, status_code=400, failure_domain="request", retryability=False,
                 visibility="client", resource_effect="unchanged", certainty="known", extra=None):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code
        self.failure_domain = failure_domain
        self.retryability = retryability
        self.visibility = visibility
        self.resource_effect = resource_effect
        self.certainty = certainty
        self.extra = extra or {}


def agent_error_response(exc):
    body = {
        "result": "error",
        "code": exc.code,
        "detail": exc.detail,
        "request_id": None,
        "retryable": exc.retryability,
        "failure_domain": exc.failure_domain,
        "visibility": exc.visibility,
        "resource_effect": exc.resource_effect,
        "certainty": exc.certainty,
    }
    body.update(sanitize_metadata(exc.extra))
    return Response(body, status=exc.status_code)


def _validation_detail(exc):
    messages = getattr(exc, "messages", None)
    if messages:
        return str(messages[0])
    return str(exc) or "Request validation failed."


def normalize_exception(exc, response=None):
    """Normalize DRF and existing Django/application exceptions for Agent clients."""
    response = response or Response(status=500)
    status_code = int(getattr(response, "status_code", 500) or 500)
    raw = getattr(response, "data", None)

    code = "INTERNAL_ERROR"
    domain = "runtime"
    retry = False
    detail = "An unexpected server error occurred."

    shell_code = str(getattr(exc, "shell_code", "") or "")
    if shell_code:
        code = shell_code
        detail = _validation_detail(exc)
        if shell_code == "CONFIRMATION_REQUIRED":
            status_code = 409
            domain = "authorization"
        elif shell_code in {"AUTHORIZATION_FAILED", "PERMISSION_DENIED"}:
            status_code = 403
            domain = "authorization"
        else:
            status_code = 400
            domain = "request"
    elif isinstance(exc, (AuthenticationFailed, NotAuthenticated)) or status_code == 401:
        code = "AUTHENTICATION_REQUIRED"
        domain = "authentication"
        status_code = 401
        detail = _validation_detail(exc)
    elif isinstance(exc, PermissionDenied) or status_code == 403:
        code = "PERMISSION_DENIED"
        domain = "authorization"
        status_code = 403
        detail = _validation_detail(exc)
    elif isinstance(exc, (ValidationError, DjangoValidationError, ValueError)) or status_code == 400:
        code = "INVALID_REQUEST"
        domain = "request"
        status_code = 400
        detail = _validation_detail(exc)
    elif isinstance(exc, Http404) or status_code == 404:
        code = "RESOURCE_NOT_FOUND"
        domain = "resource"
        status_code = 404
        detail = _validation_detail(exc)
    elif status_code == 409:
        code = "CONFLICT"
        domain = "resource"
        detail = _validation_detail(exc)
    elif status_code == 429:
        code = "RATE_LIMITED"
        domain = "infrastructure"
        retry = True
        detail = _validation_detail(exc)

    if isinstance(raw, dict):
        code = str(raw.get("code") or code)
        if status_code < 500:
            detail = str(raw.get("detail") or raw.get("error") or detail)
    elif isinstance(raw, str) and status_code < 500:
        detail = raw

    response.status_code = status_code
    response.data = {
        "result": "error",
        "code": code,
        "detail": detail,
        "request_id": None,
        "retryable": retry,
        "failure_domain": domain,
        "visibility": "client",
        "resource_effect": "unchanged",
        "certainty": "known",
    }
    return response
