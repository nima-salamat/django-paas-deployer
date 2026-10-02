"""Shared authentication, error handling and audit infrastructure for Agent APIs."""
from __future__ import annotations

import time
from functools import wraps

from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from ..application import audit
from ..authentication import AgentTokenAuthentication
from ..errors import AgentError, agent_error_response, normalize_exception
from ..permissions import AgentScopePermission, IsAgentAuthenticated
from ..security import client_ip, extract_sensitive_request_values, get_request_id, sanitize_error_payload, sanitize_metadata
from ..throttling import AgentRateThrottle


def complete_error(response, request, *, suppress_sensitive_fields=False):
    status_code = int(getattr(response, "status_code", 500))
    if status_code < 400:
        return response
    data = getattr(response, "data", None)
    if isinstance(data, dict) and data.get("result") == "error" and data.get("code"):
        body = dict(data)
    else:
        mapping = {
            401: ("AUTHENTICATION_REQUIRED", "authentication", False),
            403: ("PERMISSION_DENIED", "authorization", False),
            404: ("RESOURCE_NOT_FOUND", "resource", False),
            409: ("CONFLICT", "resource", False),
            413: ("UPLOAD_TOO_LARGE", "storage", False),
            422: ("UNSUPPORTED_CAPABILITY", "request", False),
            429: ("RATE_LIMITED", "infrastructure", True),
        }
        code, domain, retry = mapping.get(
            status_code,
            ("INVALID_REQUEST" if status_code < 500 else "INTERNAL_ERROR",
             "request" if status_code < 500 else "runtime", False),
        )
        detail = data.get("detail") or data.get("error") if isinstance(data, dict) else str(data or "")
        body = {
            "result": "error", "code": code, "detail": detail or "Request failed.",
            "request_id": getattr(request, "agent_request_id", None),
            "retryable": retry, "failure_domain": domain, "visibility": "client",
            "resource_effect": "unchanged", "certainty": "known",
        }
        if isinstance(data, dict):
            for key in ("errors", "action", "missing_scopes", "supported_inputs"):
                if key in data:
                    body[key] = sanitize_metadata(data[key])
    if suppress_sensitive_fields:
        body = sanitize_error_payload(
            body,
            secret_values=extract_sensitive_request_values(getattr(request, "data", {})),
        )
    response.data = sanitize_metadata(body)
    return response


def idempotent(fn):
    @wraps(fn)
    def wrapped(self, request, *args, **kwargs):
        from ..application import begin_idempotency, complete_idempotency, abandon_idempotency
        row = replay = None
        try:
            row, replay = begin_idempotency(request.agent, request)
            if replay is not None:
                response = Response(replay.response_body or {}, status=replay.status_code or 200)
                self.audit_metadata = {"idempotent_replay": True}
                return response
            response = fn(self, request, *args, **kwargs)
            complete_idempotency(
                row, response,
                store_body=bool(getattr(self, "idempotency_store_response", True)),
            )
            return response
        except Exception:
            abandon_idempotency(row)
            raise
    return wrapped


def _audit_resource_id(kwargs, data):
    for key in ("service_id", "deployment_id", "revision_id", "volume_id", "network_id", "plan_id"):
        value = kwargs.get(key)
        if value:
            return str(value)
    if isinstance(data, dict):
        if data.get("id"):
            return str(data["id"])
        for container_key in ("service", "deployment", "revision", "resource"):
            value = data.get(container_key)
            if isinstance(value, dict) and value.get("id"):
                return str(value["id"])
    return ""


class AgentAPIView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [AgentRateThrottle]
    throttle_scope = "read"
    required_scopes = ()
    required_scopes_by_method = {}
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    audit_action = "agent.request"
    audit_resource_type = ""
    audit_mutating = False
    idempotency_store_response = True
    suppress_error_fields = False
    agent_contract_path = None

    def get_agent_contract_path(self, request):
        return self.agent_contract_path

    def initial(self, request, *args, **kwargs):
        request.agent_request_id = get_request_id(request)
        self._started_at = time.monotonic()
        super().initial(request, *args, **kwargs)

    def handle_exception(self, exc):
        if isinstance(exc, AgentError):
            return agent_error_response(exc)
        return normalize_exception(exc, super().handle_exception(exc))

    def finalize_response(self, request, response, *args, **kwargs):
        response = complete_error(
            response,
            request,
            suppress_sensitive_fields=bool(getattr(self, "suppress_error_fields", False)),
        )
        try:
            response["X-Request-ID"] = str(request.agent_request_id)
            if isinstance(getattr(response, "data", None), dict) and response.data.get("result") == "error":
                response.data["request_id"] = str(request.agent_request_id)
        except Exception:
            pass
        try:
            status_code = int(response.status_code)
            data = response.data if isinstance(response.data, dict) else {}
            audit_metadata = dict(getattr(self, "audit_metadata", {}) or {})
            audit_metadata.update({
                "method": str(getattr(request, "method", "") or ""),
                "path": str(getattr(request, "path", "") or "")[:512],
                "client_ip": client_ip(request),
                "agent_id": str(getattr(getattr(request, "agent", None), "pk", "") or ""),
                "credential_id": str(getattr(getattr(request, "agent_credential", None), "pk", "") or ""),
            })
            audit(
                request=request,
                action=self.audit_action,
                success=200 <= status_code < 400,
                status_code=status_code,
                resource_type=self.audit_resource_type,
                resource_id=_audit_resource_id(kwargs, data),
                error_code=str(data.get("code") or ""),
                failure_domain=str(data.get("failure_domain") or ""),
                retryability=bool(data.get("retryable")),
                resource_effect=(
                    "queued" if status_code == 202
                    else "changed" if self.audit_mutating and 200 <= status_code < 400
                    else "unchanged"
                ),
                duration_ms=int(max(0, (time.monotonic() - self._started_at) * 1000)),
                metadata=audit_metadata,
            )
        except Exception:
            pass
        return super().finalize_response(request, response, *args, **kwargs)


class AgentPublicAPIView(AgentAPIView):
    pass


class AgentSecuredAPIView(AgentAPIView):
    authentication_classes = [AgentTokenAuthentication]
    permission_classes = [IsAgentAuthenticated, AgentScopePermission]


class AgentPage(AgentSecuredAPIView):
    page_size = 25

    def paginate(self, request, queryset, serializer):
        p = PageNumberPagination()
        p.page_size = self.page_size
        p.page_size_query_param = "page_size"
        p.max_page_size = 100
        page = p.paginate_queryset(queryset, request)
        return (
            p.get_paginated_response(serializer(page, many=True).data)
            if page is not None
            else Response({"results": serializer(queryset, many=True).data})
        )
