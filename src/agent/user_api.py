"""Authenticated browser API for managing the current user's PassDeployer Agents."""
from __future__ import annotations

from datetime import timedelta

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from auth_users.authentication import SessionJWTAuthentication

from .application import (
    audit,
    create_enrollment,
    issue_access_credential,
    rotate_access_credentials,
    set_agent_status,
)
from .manifest import render_agent_manifest
from .models import Agent, AgentAuditEvent, AgentCredential
from .scopes import (
    ALL_SCOPES,
    DEFAULT_SCOPES,
    DESTRUCTIVE_SCOPES,
    HIGH_RISK_SCOPES,
    SCOPE_LABELS,
    scope_categories,
    validate_scopes,
)


class AgentManagementBase(APIView):
    authentication_classes = [SessionJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _agent_queryset(self):
        return Agent.objects.filter(user=self.request.user).prefetch_related("credentials")

    def _agent(self, agent_id):
        return get_object_or_404(self._agent_queryset(), pk=agent_id)


def _dt(value):
    return value.isoformat() if value else None


def _credential_payload(credential, *, include_token=None):
    payload = {
        "id": str(credential.pk),
        "prefix": credential.token_prefix,
        "token_type": credential.token_type,
        "expires_at": _dt(credential.expires_at),
        "revoked_at": _dt(credential.revoked_at),
        "last_used_at": _dt(credential.last_used_at),
        "last_used_ip": credential.last_used_ip,
        "created_at": _dt(credential.created_at),
        "updated_at": _dt(credential.updated_at),
        "active": credential.is_active(),
    }
    if include_token is not None:
        payload["token"] = include_token
    return payload


def _agent_payload(agent):
    credentials = list(agent.credentials.all())
    active = [c for c in credentials if c.is_active()]
    return {
        "id": str(agent.pk),
        "name": agent.name,
        "description": agent.description,
        "status": agent.status,
        "scopes": sorted(agent.scopes or []),
        "scope_count": len(agent.scopes or []),
        "metadata": agent.metadata or {},
        "created_at": _dt(agent.created_at),
        "updated_at": _dt(agent.updated_at),
        "last_used_at": _dt(agent.last_used_at),
        "disabled_at": _dt(agent.disabled_at),
        "revoked_at": _dt(agent.revoked_at),
        "credential_count": len(credentials),
        "active_credential_count": len(active),
    }


def _validate_agent_payload(data, *, partial=False):
    if not isinstance(data, dict):
        return None, {"detail": "A JSON object is required."}

    values = {}
    if not partial or "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            return None, {"name": ["This field is required."]}
        if len(name) > 100:
            return None, {"name": ["Ensure this field has no more than 100 characters."]}
        values["name"] = name

    if "description" in data:
        description = str(data.get("description") or "")
        if len(description) > 10000:
            return None, {"description": ["Ensure this field has no more than 10000 characters."]}
        values["description"] = description
    elif not partial:
        values["description"] = ""

    if "scopes" in data:
        raw_scopes = data.get("scopes")
        if not isinstance(raw_scopes, (list, tuple, set)):
            return None, {"scopes": ["Must be a list of scope names."]}
        try:
            values["scopes"] = validate_scopes(raw_scopes)
        except ValueError as exc:
            return None, {"scopes": [str(exc)]}
    elif not partial:
        values["scopes"] = sorted(DEFAULT_SCOPES)

    if "metadata" in data:
        if not isinstance(data.get("metadata"), dict):
            return None, {"metadata": ["Must be an object."]}
        values["metadata"] = dict(data["metadata"])
    elif not partial:
        values["metadata"] = {}

    return values, None


class AgentScopeCatalogView(AgentManagementBase):
    def get(self, request):
        categories = scope_categories(ALL_SCOPES)
        scope_rows = []
        for name in sorted(ALL_SCOPES):
            category = next((key for key, items in categories.items() if name in items), "other")
            scope_rows.append(
                {
                    "name": name,
                    "label": SCOPE_LABELS.get(name, name),
                    "category": category,
                    "high_risk": name in HIGH_RISK_SCOPES,
                    "destructive": name in DESTRUCTIVE_SCOPES,
                    "default": name in DEFAULT_SCOPES,
                }
            )
        return Response(
            {
                "api_version": "v1",
                "scopes": scope_rows,
                "categories": {
                    key: [{"name": s, "label": SCOPE_LABELS.get(s, s)} for s in items]
                    for key, items in categories.items()
                },
                "defaults": sorted(DEFAULT_SCOPES),
                "high_risk": sorted(HIGH_RISK_SCOPES),
                "destructive": sorted(DESTRUCTIVE_SCOPES),
            }
        )


class AgentListCreateView(AgentManagementBase):
    def get(self, request):
        paginator = PageNumberPagination()
        paginator.page_size = 25
        paginator.page_size_query_param = "page_size"
        paginator.max_page_size = 100
        queryset = self._agent_queryset().order_by("name", "created_at")
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([_agent_payload(agent) for agent in page])

    def post(self, request):
        values, errors = _validate_agent_payload(request.data)
        if errors:
            return Response({"detail": "Validation failed.", "errors": errors}, status=status.HTTP_400_BAD_REQUEST)
        if Agent.objects.filter(user=request.user, name=values["name"]).exists():
            return Response(
                {"detail": "An Agent with this name already exists.", "code": "AGENT_NAME_EXISTS"},
                status=status.HTTP_409_CONFLICT,
            )
        agent = Agent.objects.create(user=request.user, **values)
        audit(
            request=request, agent=agent, user=request.user, action="browser.agent.create",
            success=True, status_code=201, resource_type="agent", resource_id=agent.pk,
            resource_effect="changed",
        )
        return Response({"result": "success", "agent": _agent_payload(agent)}, status=status.HTTP_201_CREATED)


class AgentDetailView(AgentManagementBase):
    def get(self, request, agent_id):
        return Response({"result": "success", "agent": _agent_payload(self._agent(agent_id))})

    def patch(self, request, agent_id):
        agent = self._agent(agent_id)
        values, errors = _validate_agent_payload(request.data, partial=True)
        if errors:
            return Response({"detail": "Validation failed.", "errors": errors}, status=status.HTTP_400_BAD_REQUEST)
        if "name" in values and Agent.objects.filter(user=request.user, name=values["name"]).exclude(pk=agent.pk).exists():
            return Response(
                {"detail": "An Agent with this name already exists.", "code": "AGENT_NAME_EXISTS"},
                status=status.HTTP_409_CONFLICT,
            )
        for key, value in values.items():
            setattr(agent, key, value)
        agent.save()
        audit(
            request=request, agent=agent, user=request.user, action="browser.agent.update",
            success=True, status_code=200, resource_type="agent", resource_id=agent.pk,
            resource_effect="changed",
        )
        return Response({"result": "success", "agent": _agent_payload(agent)})


class AgentCredentialListView(AgentManagementBase):
    def get(self, request, agent_id):
        agent = self._agent(agent_id)
        paginator = PageNumberPagination()
        paginator.page_size = 25
        paginator.page_size_query_param = "page_size"
        paginator.max_page_size = 100
        page = paginator.paginate_queryset(agent.credentials.all().order_by("-created_at"), request, view=self)
        return paginator.get_paginated_response([_credential_payload(c) for c in page])

    def post(self, request, agent_id):
        agent = self._agent(agent_id)
        if agent.status != Agent.Status.ACTIVE:
            return Response(
                {"detail": "Only active Agents can issue credentials.", "code": "AGENT_NOT_ACTIVE"},
                status=status.HTTP_409_CONFLICT,
            )

        expires_at = None
        raw_expires_at = request.data.get("expires_at")
        if raw_expires_at:
            expires_at = parse_datetime(str(raw_expires_at))
            if expires_at is None:
                return Response({"errors": {"expires_at": ["Invalid ISO-8601 datetime."]}}, status=status.HTTP_400_BAD_REQUEST)
            if timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at)
            if expires_at <= timezone.now():
                return Response({"errors": {"expires_at": ["Expiry must be in the future."]}}, status=status.HTTP_400_BAD_REQUEST)

        if request.data.get("expires_in_days") is not None:
            try:
                days = int(request.data.get("expires_in_days"))
            except (TypeError, ValueError):
                days = 0
            if not 1 <= days <= 3650:
                return Response({"errors": {"expires_in_days": ["Use a value between 1 and 3650."]}}, status=status.HTTP_400_BAD_REQUEST)
            expires_at = timezone.now() + timedelta(days=days)

        credential, token = issue_access_credential(
            agent,
            expires_at=expires_at,
            metadata={"issued_via": "browser_api", "issued_by_user": str(request.user.pk)},
        )
        audit(
            request=request, agent=agent, user=request.user, credential=credential,
            action="browser.credential.issue", success=True, status_code=201,
            resource_type="agent_credential", resource_id=credential.pk, resource_effect="changed",
        )
        response = Response(
            {
                "result": "success",
                "credential": _credential_payload(credential, include_token=token),
                "warning": "This token is shown only once. Store it in a secure secret store.",
            },
            status=status.HTTP_201_CREATED,
        )
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class AgentCredentialRotateView(AgentManagementBase):
    def post(self, request, agent_id):
        agent = self._agent(agent_id)
        try:
            credential, token = rotate_access_credentials(
                agent,
                metadata={"rotated_via": "browser_api", "rotated_by_user": str(request.user.pk)},
            )
        except Exception as exc:
            return Response(
                {"detail": str(exc), "code": getattr(exc, "code", "CREDENTIAL_ROTATION_FAILED")},
                status=getattr(exc, "status_code", status.HTTP_409_CONFLICT),
            )
        audit(
            request=request, agent=agent, user=request.user, credential=credential,
            action="browser.credential.rotate", success=True, status_code=201,
            resource_type="agent", resource_id=agent.pk, resource_effect="changed",
            metadata={"revoked_previous_credentials": True},
        )
        response = Response(
            {
                "result": "success",
                "credential": _credential_payload(credential, include_token=token),
                "warning": "All previously active credentials were revoked. This token is shown only once.",
            },
            status=status.HTTP_201_CREATED,
        )
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class AgentCredentialRevokeView(AgentManagementBase):
    def post(self, request, agent_id, credential_id):
        agent = self._agent(agent_id)
        credential = get_object_or_404(AgentCredential, pk=credential_id, agent=agent)
        if credential.revoked_at is None:
            credential.revoked_at = timezone.now()
            credential.save(update_fields=["revoked_at", "updated_at"])
        audit(
            request=request, agent=agent, user=request.user, credential=credential,
            action="browser.credential.revoke", success=True, status_code=200,
            resource_type="agent_credential", resource_id=credential.pk, resource_effect="changed",
        )
        return Response({"result": "success", "credential": _credential_payload(credential)})


class AgentStatusView(AgentManagementBase):
    status_map = {
        "disable": Agent.Status.DISABLED,
        "enable": Agent.Status.ACTIVE,
        "revoke": Agent.Status.REVOKED,
    }

    def post(self, request, agent_id, action):
        agent = self._agent(agent_id)
        next_status = self.status_map.get(action)
        if next_status is None:
            return Response({"detail": "Unsupported Agent action."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            agent = set_agent_status(agent, next_status)
        except Exception as exc:
            return Response(
                {"detail": str(exc), "code": getattr(exc, "code", "AGENT_STATUS_FAILED")},
                status=getattr(exc, "status_code", status.HTTP_409_CONFLICT),
            )
        audit(
            request=request, agent=agent, user=request.user, action=f"browser.agent.{action}",
            success=True, status_code=200, resource_type="agent", resource_id=agent.pk,
            resource_effect="changed",
        )
        return Response({"result": "success", "agent": _agent_payload(agent)})


class AgentAuditView(AgentManagementBase):
    def get(self, request, agent_id):
        agent = self._agent(agent_id)
        paginator = PageNumberPagination()
        paginator.page_size = 50
        paginator.page_size_query_param = "page_size"
        paginator.max_page_size = 100
        page = paginator.paginate_queryset(
            AgentAuditEvent.objects.filter(agent=agent).order_by("-occurred_at"), request, view=self
        )
        payload = [
            {
                "id": str(event.pk),
                "action": event.action,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
                "request_id": event.request_id,
                "occurred_at": _dt(event.occurred_at),
                "success": event.success,
                "http_status": event.http_status,
                "error_code": event.error_code,
                "failure_domain": event.failure_domain,
                "retryability": event.retryability,
                "resource_effect": event.resource_effect,
                "certainty": event.certainty,
                "duration_ms": event.duration_ms,
                "metadata": event.metadata or {},
            }
            for event in page
        ]
        return paginator.get_paginated_response(payload)


class AgentManifestManagementView(AgentManagementBase):
    def post(self, request, agent_id):
        agent = self._agent(agent_id)
        if agent.status != Agent.Status.ACTIVE:
            return Response(
                {"detail": "Only active Agents can generate a bootstrap manifest.", "code": "AGENT_NOT_ACTIVE"},
                status=status.HTTP_409_CONFLICT,
            )
        enrollment, row = create_enrollment(agent, request=request)
        content = render_agent_manifest(agent, enrollment, request=request)
        audit(
            request=request, agent=agent, user=request.user, action="browser.agent_manifest.generate",
            success=True, status_code=200, resource_type="agent", resource_id=agent.pk,
            resource_effect="unchanged",
            metadata={"enrollment_prefix": row.token_prefix, "enrollment_expires_at": row.expires_at.isoformat()},
        )
        response = HttpResponse(
            content,
            content_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="AGENT-{agent.pk}.md"'},
        )
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response
