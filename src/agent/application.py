
from __future__ import annotations
import hmac

import json
import secrets
import zipfile
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .errors import AgentError
from .models import Agent, AgentAuditEvent, AgentCredential, AgentEnrollmentToken, AgentIdempotencyRecord
from .security import client_ip, issue_raw_access_token, issue_raw_enrollment_token, sanitize_metadata, scrub_text, stable_json_hash, token_hash, token_prefix


class RequestProxy:
    def __init__(self, request, *, data=None):
        self._request = request
        self._data = request.data if data is None else data

    @property
    def data(self):
        return self._data

    def __getattr__(self, name):
        return getattr(self._request, name)


def has_scope(agent, *scopes):
    selected = set(agent.scopes or [])
    return all(scope in selected for scope in scopes)


def require_scopes(agent, *scopes):
    missing = sorted(set(scopes) - set(agent.scopes or []))
    if missing:
        raise AgentError("INSUFFICIENT_SCOPE", "The Agent does not have the required scope(s).", status_code=403,
                         failure_domain="authorization", extra={"missing_scopes": missing})


def ensure_service_access(service, user, *, action="can_view", owner_only=False):
    if str(service.user_id) == str(user.id):
        return None
    if owner_only:
        raise AgentError("PERMISSION_DENIED", "This operation is restricted to the service owner.", status_code=403,
                         failure_domain="authorization")
    from services.api.sharing import user_can_access_service
    allowed, share = user_can_access_service(service, user, action=action)
    if not allowed:
        raise AgentError("PERMISSION_DENIED", f"You do not have permission to perform '{action}' on this service.",
                         status_code=403, failure_domain="authorization", extra={"share_action": action})
    return share


def call_api_view_handler(api_view_function, request, method, *args, data=None, **kwargs):
    """Call an existing Django/DRF API boundary in-process, never over HTTP."""
    proxy = RequestProxy(request, data=data)
    cls = getattr(api_view_function, "cls", None)
    if cls is not None:
        instance = cls()
        instance.request = proxy
        instance.args = ()
        instance.kwargs = kwargs
        instance.format_kwarg = None
        handler = getattr(instance, method.lower())
        return handler(proxy, *args, **kwargs)
    return api_view_function(proxy, *args, **kwargs)


def call_runtime_api(api_view_function, request, service_id, *, data=None):
    """Adapt the Agent call to the existing runtime API's real Python signature."""
    import inspect
    try:
        original = inspect.unwrap(api_view_function)
        parameters = inspect.signature(original).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "service_id" in parameters:
        return call_api_view_handler(api_view_function, request, "post", service_id, data=data)
    return call_api_view_handler(api_view_function, request, "post", data=data)

def call_viewset_action(viewset_cls, action_name, request, *, pk=None, data=None):
    """Invoke an existing ViewSet application boundary in-process.

    CRUD methods do not all share the same Python signature: detail actions
    accept ``pk`` while collection ``create`` generally does not. The adapter
    therefore passes ``pk`` only when the target operation explicitly needs it.
    """
    proxy = RequestProxy(request, data=data)
    view = viewset_cls()
    view.request = proxy
    view.args = ()
    view.kwargs = {"pk": str(pk)} if pk is not None else {}
    view.action = action_name
    view.format_kwarg = None
    handler = getattr(view, action_name)
    if pk is None:
        return handler(proxy)
    return handler(proxy, pk=pk)
def _viewset_request(user):
    from types import SimpleNamespace
    return SimpleNamespace(
        user=user,
        data={},
        query_params={},
        GET={},
        method="GET",
        META={},
    )


def accessible_service_queryset(user, *, include_shared=False):
    """Reuse ServiceViewSet visibility rules for list vs resource operations.

    The user-facing ServiceViewSet deliberately returns only owned Services for
    ``list`` but includes active shared Services for retrieve/update actions.
    Agent resource operations must use the latter path so ServiceShare checks
    can run before allowing a shared resource action.
    """
    from services.api.user_services import ServiceViewSet
    view = ServiceViewSet()
    view.request = _viewset_request(user)
    view.action = "retrieve" if include_shared else "list"
    return (
        view.get_queryset()
        .select_related("user", "plan", "network", "active_revision", "selected_deploy")
        .prefetch_related("processes", "endpoints", "volumes")
        .distinct()
        .order_by("-created_at")
    )

def get_service(service_id, user, *, action="can_view", owner_only=False):
    service = accessible_service_queryset(user, include_shared=True).filter(pk=service_id).first()
    if service is None:
        raise AgentError("SERVICE_NOT_FOUND", "Service not found.", status_code=404, failure_domain="resource")
    ensure_service_access(service, user, action=action, owner_only=owner_only)
    return service


def service_payload(service):
    revision = getattr(service, "active_revision", None)
    deploy = getattr(revision, "source_deploy", None) if revision else getattr(service, "selected_deploy", None)
    plan = getattr(service, "plan", None)
    network = getattr(service, "network", None)
    processes = [{
        "id": str(p.pk), "name": getattr(p, "name", ""), "type": getattr(p, "process_type", ""), "command": getattr(p, "command", None),
        "entrypoint": getattr(p, "entrypoint", None), "replicas": getattr(p, "replicas", None), "healthcheck": getattr(p, "healthcheck", None),
        "resources": getattr(p, "resources", None),
    } for p in service.processes.all()]
    endpoints = [{
        "id": str(e.pk), "name": getattr(e, "name", ""), "target_port": getattr(e, "target_port", None),
        "published_port": getattr(e, "published_port", None), "protocol": getattr(e, "protocol", None), "exposure": getattr(e, "exposure", None),
        "hostname": getattr(e, "hostname", None), "path": getattr(e, "path", None), "tls": getattr(e, "tls", None), "enabled": getattr(e, "enabled", True),
    } for e in service.endpoints.all() if e.enabled]
    volumes = [{
        "id": str(v.pk), "name": getattr(v, "name", ""), "size_mb": getattr(v, "size_mb", None),
        "mode": v.get_mode_for_service(service) if hasattr(v, "get_mode_for_service") else getattr(v, "default_mode", None),
        "bind": v.get_bind_for_service(service) if hasattr(v, "get_bind_for_service") else getattr(v, "default_bind", None),
        "released_at": getattr(v, "released_at", None),
    } for v in service.volumes.all()]
    return {
        "id": str(service.pk), "name": service.name,
        "owner": {"id": str(service.user_id), "username": getattr(service.user, "username", None)},
        "plan": ({"id": str(plan.pk), "name": plan.name, "platform": plan.platform, "plan_type": plan.plan_type} if plan else None),
        "platform": str(getattr(plan, "platform", "") or ""),
        "source_kind": service.source_kind,
        "desired_state": service.desired_state, "status": service.status,
        "read_only": bool(service.read_only),
        "active_revision": ({"id": str(revision.pk), "revision": revision.revision_number, "state": revision.state} if revision else None),
        "deployment": (deployment_payload(deploy) if deploy else None),
        "network": ({"id": str(network.pk), "name": network.name, "description": network.description} if network else None),
        "processes": processes, "endpoints": endpoints, "volumes": volumes,
        "timestamps": {
            "created_at": service.created_at, "updated_at": service.updated_at,
            "deploy_started": service.deploy_started, "deployed_at": service.deployed_at,
        },
    }


def create_service_from_plan(request, payload, *, plan_id=None):
    """High-level plan application workflow built on the existing Service API."""
    data = dict(payload or {})
    if plan_id is not None:
        supplied = data.get("plan")
        if supplied and str(supplied) != str(plan_id):
            raise AgentError(
                "INVALID_REQUEST",
                "The URL plan_id and request plan must match.",
                status_code=400,
            )
        data["plan"] = str(plan_id)
    if not data.get("plan"):
        raise AgentError("INVALID_REQUEST", "plan is required.", status_code=400)

    from plans.models import Plan
    plan = Plan.objects.filter(pk=data["plan"]).first()
    if plan is None:
        raise AgentError("PLAN_NOT_FOUND", "Plan not found.", status_code=404, failure_domain="resource")

    workflow_network = None
    create_network_requested = bool(data.pop("create_network", False))
    network_name = data.pop("network_name", None)
    if not data.get("network") and create_network_requested:
        require_scopes(request.agent, "service_networks.write")
        workflow_network = create_network(
            request,
            {
                "name": network_name or f"{data.get('name') or 'service'}-network",
                "description": "Created by Agent service-from-plan workflow",
            },
        )
        data["network"] = str(workflow_network.pk)

    service = create_service(request, data)
    return service, workflow_network


def manage_plan(request, action, plan_id=None, data=None):
    """Mutate plans through the existing PlanAdminViewSet application boundary.

    This preserves the canonical plan validation, cache invalidation, and
    staff/rule authorization behavior instead of creating a second mutation
    implementation inside the Agent facade.
    """
    from plans.apis import PlanAdminViewSet
    from plans.models import Plan

    response = call_viewset_action(
        PlanAdminViewSet, action, request, pk=plan_id, data=data,
    )
    if response.status_code >= 400:
        body = response.data if isinstance(response.data, dict) else {}
        raise AgentError(
            "PLAN_OPERATION_FAILED",
            body.get("detail") or body.get("error") or body.get("message") or "Plan operation failed.",
            status_code=response.status_code,
            failure_domain="resource",
            extra={"validation": sanitize_metadata(body)},
        )

    if action == "destroy":
        return None

    payload = response.data if isinstance(response.data, dict) else {}
    nested = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    resolved_id = nested.get("id") or payload.get("id") or plan_id
    plan = Plan.objects.filter(pk=resolved_id).first()
    if plan is None:
        raise AgentError(
            "PLAN_OPERATION_FAILED",
            "Plan operation succeeded but the plan could not be reloaded.",
            status_code=500,
            failure_domain="resource",
        )
    return plan

def require_plan_management(user, action: str):
    """Reuse the existing plans.apis staff/rule model for Agent plan administration."""
    from plans.apis import _user_has_rule
    if getattr(user, "is_superuser", False):
        return
    if not getattr(user, "is_staff", False) or not _user_has_rule(user, "plans.manage"):
        raise AgentError(
            "PERMISSION_DENIED",
            "Plan management requires the existing staff plans.manage permission.",
            status_code=403,
            failure_domain="authorization",
        )


def create_service(request, payload):
    from services.api.user_services import ServiceViewSet

    network_id = payload.get("network")
    if not network_id:
        raise AgentError("NETWORK_REQUIRED", "A Private Network is required to create a service.", status_code=409,
                         failure_domain="resource")
    from services.models import PrivateNetwork
    if not PrivateNetwork.objects.filter(pk=network_id, user=request.user).exists():
        raise AgentError("NETWORK_REQUIRED", "The supplied network does not belong to the authenticated user.",
                         status_code=409, failure_domain="authorization")
    data = dict(payload)
    data["user"] = str(request.user.pk)
    response = call_viewset_action(ServiceViewSet, "create", request, data=data)
    if response.status_code >= 400:
        raise AgentError("SERVICE_CREATE_FAILED", response.data.get("error") or response.data.get("detail") or "Service creation failed.",
                         status_code=response.status_code, failure_domain="resource", extra={"validation": sanitize_metadata(response.data)})
    sid = response.data.get("id") or response.data.get("pk")
    return get_service(sid, request.user, action="can_view")


def update_service(request, service_id, payload):
    service = get_service(service_id, request.user, action="can_view")
    response = call_viewset_action(__import__("services.api.user_services", fromlist=["ServiceViewSet"]).ServiceViewSet,
                                   "update", request, pk=service.pk, data=dict(payload))
    if response.status_code >= 400:
        return response
    service.refresh_from_db()
    return {"result": "success", "service": service_payload(service)}


def deployment_queryset(user):
    # Reuse DeployViewSet's established ownership/share queryset.
    from deploy.apis import DeployViewSet
    view = DeployViewSet()
    view.request = _viewset_request(user)
    view.action = "list"
    return (
        view.get_queryset()
        .select_related("service", "service__user", "service__plan", "created_by", "revision")
        .distinct()
        .order_by("-created_at")
    )


def deployment_payload(deploy):
    return {
        "id": str(deploy.pk), "release_id": str(getattr(deploy, "release_id", "")), "name": getattr(deploy, "name", ""),
        "service_id": str(getattr(deploy, "service_id", "")), "revision_id": str(deploy.revision_id) if getattr(deploy, "revision_id", None) else None,
        "version": str(getattr(deploy, "version", "")), "status": getattr(deploy, "status", ""), "stage": getattr(deploy, "stage", ""),
        "progress": getattr(deploy, "progress", 0), "status_message": getattr(deploy, "status_message", ""), "error_message": getattr(deploy, "error_message", ""),
        "rollback_status": getattr(deploy, "rollback_status", ""), "health_status": getattr(deploy, "health_status", ""),
        "container_status": getattr(deploy, "container_status", ""), "image_status": getattr(deploy, "image_status", ""),
        "volume_status": getattr(deploy, "volume_status", ""), "network_status": getattr(deploy, "network_status", ""),
        "source_revision": getattr(deploy, "source_revision", ""), "image_ref": getattr(deploy, "image_ref", ""), "image_digest": getattr(deploy, "image_digest", ""),
        "runtime_revision_id": str(deploy.runtime_revision_id) if getattr(deploy, "runtime_revision_id", None) else None,
        "zip_file": bool(getattr(deploy, "zip_file", None)), "created_by": str(getattr(deploy, "created_by_id", None)) if getattr(deploy, "created_by_id", None) else None,
        "execution_task_id": deploy.execution_task_id or None, "started_at": getattr(deploy, "started_at", None),
        "completed_at": getattr(deploy, "completed_at", None), "created_at": getattr(deploy, "created_at", None), "updated_at": getattr(deploy, "updated_at", None),
    }


def get_deployment(deployment_id, user, *, action="can_view"):
    from deploy.models import Deploy
    deploy = Deploy.objects.select_related("service", "service__user", "service__plan", "created_by", "revision").filter(pk=deployment_id).first()
    if deploy is None:
        raise AgentError("DEPLOYMENT_NOT_FOUND", "Deployment not found.", status_code=404, failure_domain="resource")
    ensure_service_access(deploy.service, user, action="can_view")
    if action != "can_view":
        from services.share_permissions import can_mutate_deploy
        if not can_mutate_deploy(deploy, user, action=action):
            raise AgentError("PERMISSION_DENIED", f"You do not have permission ({action}) for this deployment.",
                             status_code=403, failure_domain="authorization")
    return deploy


def create_deployment(request, payload):
    from deploy.apis import DeployViewSet
    data = dict(payload); data["service"] = str(data.get("service") or "")
    if not data["service"]:
        raise AgentError("INVALID_REQUEST", "service is required.", status_code=400)
    get_service(data["service"], request.user, action="can_deploy_add")
    source = str(data.pop("source", data.pop("source_kind", "archive")) or "archive").strip().lower()
    if source not in {"archive", "zip", "database", "database_native"}:
        raise AgentError("UNSUPPORTED_CAPABILITY", "Git and existing-image inputs are not first-class production deployment inputs.",
                         status_code=422, failure_domain="request", extra={"supported_inputs": ["archive", "database_native"]})
    if "config" in data and isinstance(data["config"], str):
        try: data["config"] = json.loads(data["config"])
        except json.JSONDecodeError as exc: raise AgentError("INVALID_REQUEST", "config must be valid JSON.", status_code=400) from exc
    response = call_viewset_action(DeployViewSet, "create", request, data=data)
    if response.status_code >= 400:
        body = response.data if isinstance(response.data, dict) else {}
        raise AgentError("DEPLOYMENT_CREATE_FAILED", body.get("detail") or body.get("error") or "Deployment creation failed.",
                         status_code=response.status_code, failure_domain="resource", extra={"validation": sanitize_metadata(body)})
    did = response.data.get("id")
    if not did:
        raise AgentError("DEPLOYMENT_CREATE_FAILED", "The deployment service did not return a deployment id.", status_code=500)
    return get_deployment(did, request.user, action="can_view")


def upload_deployment_zip(request, deployment_id):
    deploy = get_deployment(deployment_id, request.user, action="can_deploy_edit")
    upload = request.FILES.get("file") or request.FILES.get("zip_file")
    if upload is None:
        raise AgentError("INVALID_REQUEST", "A ZIP file is required in multipart field 'file'.", status_code=400)
    from deploy.models import MAX_ZIP_SIZE_MB
    max_bytes = int(MAX_ZIP_SIZE_MB * 1024 * 1024)
    if int(getattr(upload, "size", 0) or 0) > max_bytes:
        raise AgentError("UPLOAD_TOO_LARGE", f"Deployment archive exceeds the {MAX_ZIP_SIZE_MB} MB limit.", status_code=413, failure_domain="storage")
    if not str(getattr(upload, "name", "") or "").lower().endswith(".zip"):
        raise AgentError("INVALID_ARCHIVE", "Only .zip deployment archives are supported.", status_code=400)
    try:
        upload.seek(0)
        valid = zipfile.is_zipfile(upload)
        upload.seek(0)
    except Exception as exc:
        raise AgentError("INVALID_ARCHIVE", "The uploaded file could not be inspected.", status_code=400) from exc
    if not valid:
        raise AgentError("INVALID_ARCHIVE", "The uploaded file is not a valid ZIP archive.", status_code=400)
    from deploy.apis import DeployViewSet
    response = call_viewset_action(DeployViewSet, "partial_update", request, pk=deploy.pk, data={"zip_file": upload})
    if response.status_code >= 400:
        body = response.data if isinstance(response.data, dict) else {}
        raise AgentError("UPLOAD_FAILED", body.get("detail") or body.get("error") or "ZIP upload failed.",
                         status_code=response.status_code, failure_domain="storage", extra={"backend": body})
    deploy.refresh_from_db()
    return deploy


def deployment_action(request, deployment_id, action):
    action_scope = {"start":"deployments.start","cancel":"deployments.cancel","redeploy":"deployments.redeploy","rebuild":"deployments.rebuild"}[action]
    share_action = {"start":"can_start","cancel":"can_stop","redeploy":"can_start","rebuild":"can_rebuild"}[action]
    require_scopes(request.agent, action_scope)
    deploy = get_deployment(deployment_id, request.user, action=share_action)
    from deploy.apis import DeployViewSet
    response = call_viewset_action(DeployViewSet, action, request, pk=deploy.pk)
    return response


def rollback_revision(request, service_id, revision_id):
    get_service(service_id, request.user, action="can_deploy_add")
    from services.api.configuration import ServiceRevisionRollbackAPIView
    return ServiceRevisionRollbackAPIView().post(RequestProxy(request), service_id, revision_id)


def runtime_logs(service_id, request):
    from logs.query import ExpiredCursorError, query_logs
    from django.utils.dateparse import parse_datetime

    def ts(key):
        raw=request.query_params.get(key)
        if not raw:return None
        value=parse_datetime(raw)
        if value is None:raise AgentError("INVALID_REQUEST","Invalid timestamp.",status_code=400)
        return value
    try:
        limit=min(max(int(request.query_params.get("limit") or 100),1),500)
        return query_logs(service_id, from_ts=ts("from"), to_ts=ts("to"),
                          level=(request.query_params.get("level") or "").strip(),
                          stream=(request.query_params.get("stream") or "").strip(),
                          q=(request.query_params.get("q") or "").strip(),
                          cursor=request.query_params.get("cursor") or None,
                          direction=(request.query_params.get("direction") or "older").strip(), limit=limit)
    except ExpiredCursorError as exc:
        raise AgentError("EXPIRED_CURSOR",str(exc),status_code=409,failure_domain="storage")
    except ValueError as exc:
        raise AgentError("INVALID_CURSOR",str(exc),status_code=400)


def issue_access_credential(agent, *, expires_at=None, metadata=None):
    raw=issue_raw_access_token()
    if expires_at is None:
        expires_at=timezone.now()+timedelta(days=max(1,int(getattr(settings,"AGENT_ACCESS_TOKEN_DEFAULT_DAYS",30))))
    credential=AgentCredential.objects.create(agent=agent,token_prefix=token_prefix(raw),token_hash=token_hash(raw),
                                              token_type=AgentCredential.TokenType.ACCESS,expires_at=expires_at,
                                              metadata=sanitize_metadata(metadata or {}))
    return credential,raw


def create_enrollment(agent, *, request=None):
    raw=issue_raw_enrollment_token(); now=timezone.now()
    ttl=max(1,min(int(getattr(settings,"AGENT_ENROLLMENT_TTL_MINUTES",10)),60))
    # Only the newest bootstrap credential remains usable for this Agent.
    AgentEnrollmentToken.objects.filter(
        agent=agent, used_at__isnull=True, expires_at__gt=now
    ).update(expires_at=now, updated_at=now)
    row=AgentEnrollmentToken.objects.create(agent=agent,token_prefix=token_prefix(raw),token_hash=token_hash(raw),
                                             expires_at=now+timedelta(minutes=ttl),issued_from_ip=client_ip(request) if request else None)
    return raw,row


@transaction.atomic
def exchange_enrollment(raw_token, *, metadata=None):
    from django.db import transaction
    from django.utils import timezone
    from .models import AgentEnrollmentToken

    raw = str(raw_token or "").strip()
    if not raw:
        raise AgentError("ENROLLMENT_EXPIRED", "The enrollment credential is missing or invalid.", status_code=401, failure_domain="authentication")

    prefix = token_prefix(raw)
    digest = token_hash(raw)
    with transaction.atomic():
        rows = (
            AgentEnrollmentToken.objects
            .select_for_update()
            .select_related("agent", "agent__user")
            .filter(token_prefix=prefix)
        )
        row = None
        for candidate in rows:
            if hmac.compare_digest(candidate.token_hash, digest):
                row = candidate
                break
        if row is None:
            raise AgentError("ENROLLMENT_EXPIRED", "The enrollment credential is missing, expired, or already used.", status_code=401, failure_domain="authentication")

        now = timezone.now()
        if row.used_at is not None or row.expires_at <= now:
            raise AgentError("ENROLLMENT_EXPIRED", "The enrollment credential is missing, expired, or already used.", status_code=401, failure_domain="authentication")
        if row.agent.status != row.agent.Status.ACTIVE or not row.agent.user.is_active:
            raise AgentError("AGENT_DISABLED", "The Agent or owning user is inactive.", status_code=403, failure_domain="authorization")

        row.used_at = now
        row.save(update_fields=["used_at", "updated_at"])
        credential, access_token = issue_access_credential(row.agent, metadata=metadata or {})
        return row.agent, credential, access_token

def begin_idempotency(agent, request):
    key = str(request.headers.get("Idempotency-Key") or "").strip()
    if not key:
        return None, None
    if len(key) > 255:
        raise AgentError("INVALID_IDEMPOTENCY_KEY", "Idempotency-Key is too long.", status_code=400)

    payload = {"query": request.META.get("QUERY_STRING", "")}
    try:
        normalized = {}
        for field, value in request.data.items():
            if hasattr(value, "name") and hasattr(value, "size"):
                original_pos = None
                try:
                    original_pos = value.tell()
                except Exception:
                    original_pos = 0
                digest = __import__("hashlib").sha256()
                try:
                    value.seek(0)
                    for chunk in value.chunks() if hasattr(value, "chunks") else iter(lambda: value.read(1024 * 1024), b""):
                        digest.update(chunk)
                finally:
                    try:
                        value.seek(original_pos or 0)
                    except Exception:
                        pass
                normalized[str(field)] = {
                    "file_name": str(value.name),
                    "size": int(value.size),
                    "content_type": getattr(value, "content_type", ""),
                    "sha256": digest.hexdigest(),
                }
            else:
                normalized[str(field)] = value
        payload["data"] = normalized
    except Exception:
        payload["data"] = {}

    rh = stable_json_hash(payload | {"method": request.method, "path": request.path})
    now = timezone.now()
    try:
        row = AgentIdempotencyRecord.objects.create(
            agent=agent, key=key, method=request.method, path=request.path, request_hash=rh,
            state="processing", expires_at=now + timedelta(hours=24),
        )
        return row, None
    except IntegrityError:
        row = AgentIdempotencyRecord.objects.filter(agent=agent, key=key, expires_at__gt=now).first()
        if row is None:
            raise AgentError("IDEMPOTENCY_RETRY", "Record expired; retry with a new key.", status_code=409)
        if row.request_hash != rh or row.method != request.method or row.path != request.path:
            raise AgentError("IDEMPOTENCY_KEY_REUSED", "Idempotency-Key was reused for a different request.", status_code=409)
        if row.state == "complete":
            return None, row
        raise AgentError(
            "IDEMPOTENCY_IN_PROGRESS",
            "The same operation is already being processed.",
            status_code=409, retryability=True, failure_domain="request",
        )

def complete_idempotency(row, response, *, store_body=True):
    if row is None:
        return
    row.state = "complete"
    row.status_code = int(response.status_code)
    if store_body and int(response.status_code) < 400:
        payload = getattr(response, "data", {})
        row.response_body = sanitize_metadata(payload if isinstance(payload, dict) else {"detail": str(payload)})
    else:
        row.response_body = {"result": "success", "status_code": int(response.status_code)}
    row.save(update_fields=["state", "status_code", "response_body", "updated_at"])


def abandon_idempotency(row):
    if row:
        try:row.delete()
        except Exception:pass


def audit(*,request,action,success,status_code=None,resource_type="",resource_id="",error_code="",failure_domain="",retryability=False,resource_effect="unchanged",certainty="known",duration_ms=None,agent=None,user=None,credential=None,metadata=None):
    try:
        user=user if user is not None else (request.user if getattr(request,"user",None) and getattr(request.user,"is_authenticated",False) else None)
        AgentAuditEvent.objects.create(agent=agent or getattr(request,"agent",None),user=user,credential=credential or getattr(request,"agent_credential",None),
          action=action,resource_type=resource_type,resource_id=str(resource_id or ""),request_id=str(getattr(request,"agent_request_id","")),
          success=bool(success),http_status=status_code,error_code=error_code,failure_domain=failure_domain,
          retryability="true" if retryability else "false",resource_effect=resource_effect,certainty=certainty,
          duration_ms=int(duration_ms) if duration_ms is not None else None,
          metadata=sanitize_metadata(metadata or {}))
    except Exception:pass


def redact_shell_result(service, result):
    values=[]
    try:
        from services.models import ServiceSecret
        from services.secret_store import decrypt_secret
        for secret in ServiceSecret.objects.filter(service=service,enabled=True).prefetch_related("versions"):
            version=next((v for v in secret.versions.all() if v.version==secret.current_version),None)
            if version:
                value=decrypt_secret(version.ciphertext)
                if value:values.append(value)
    except Exception:
        pass
    try:
        from services.models import ServiceDatabaseBinding
        for binding in ServiceDatabaseBinding.objects.filter(service=service).select_related("database"):
            credential=getattr(binding.database,"credential",None)
            password=getattr(credential,"password_ciphertext","") if credential else ""
            if password:
                from services.secret_store import decrypt_secret
                value=decrypt_secret(password)
                if value:values.append(value)
    except Exception:
        pass
    out=dict(result or {})
    out["stdout"]=scrub_text(out.get("stdout",""),values)
    out["stderr"]=scrub_text(out.get("stderr",""),values)
    out["command"]=scrub_text(out.get("command",""),values)
    return out



def network_queryset(user):
    from services.models import PrivateNetwork
    return PrivateNetwork.objects.filter(user=user).select_related("user").order_by("name")


def network_payload(network):
    return {"id":str(network.pk),"name":network.name,"description":network.description,"created_at":network.created_at,"updated_at":network.updated_at}


def create_network(request,payload):
    from services.api.user_services import PrivateNetworkViewSet
    data=dict(payload or {})
    data["user"]=str(request.user.pk)
    if not data.get("name"):
        raise AgentError("INVALID_REQUEST","name is required.",status_code=400)
    response=call_viewset_action(PrivateNetworkViewSet,"create",request,data=data)
    if response.status_code>=400:
        body=response.data if isinstance(response.data,dict) else {}
        raise AgentError("NETWORK_CREATE_FAILED",body.get("detail") or body.get("error") or "Network creation failed.",status_code=response.status_code,failure_domain="resource",extra={"backend":body})
    from services.models import PrivateNetwork
    return PrivateNetwork.objects.get(pk=response.data.get("id") or response.data.get("pk"))


def update_network(request,network_id,payload):
    from services.api.user_services import PrivateNetworkViewSet
    network=network_queryset(request.user).filter(pk=network_id).first()
    if network is None:
        raise AgentError("NETWORK_NOT_FOUND","Network not found.",status_code=404,failure_domain="resource")
    response=call_viewset_action(PrivateNetworkViewSet,"update",request,pk=network.pk,data=dict(payload))
    if response.status_code>=400:return response
    return network_queryset(request.user).get(pk=network.pk)
