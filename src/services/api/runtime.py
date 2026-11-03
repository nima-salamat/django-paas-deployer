import functools
import logging
import os
import tarfile
import tempfile
import uuid
from django.db import transaction
from django.conf import settings
from django.http import FileResponse
from ..models import Service, PrivateNetwork, Volume
from deploy.models import Deploy, DeploymentStatusChoices
from django.shortcuts import get_object_or_404
from ..serializers import (
    PrivateNetworkSerializer,
    ServiceSerializer,
    VolumeSerializer,
    GetServiceSerializer,
)
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from auth_users.authentication import SessionJWTAuthentication as JWTAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import api_view, authentication_classes, permission_classes, action
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from deployments.celery.tasks import deploy as start_service
from deployments.celery.tasks import stop as stop_service
from deployments.celery.tasks import run_db_deploy  # DB platforms
from core.global_settings.config import SERVICE_STATUS_CHOICES
from core.utils import make_uuid4
from deployments.core.db_deployer import DB_PLATFORMS, DBDeployer
from deployments.core.deploy import Deploy as OrchestratorDeploy
from services.revisioning import get_active_deploy
from deployments.core.manager.container_manager import Container
from deployments.core.swarm import SwarmRuntime, swarm_enabled
from deployments.core.manager.client_manager import Client
from deployments.common.exceptions import StaleDeploymentWorkerError
from docker.errors import NotFound as DockerNotFound


logger = logging.getLogger(__name__)

def _sync_ready_app_parent_status(service_id):
    try:
        from app_catalog.lifecycle import sync_application_status_for_service
        sync_application_status_for_service(service_id)
    except Exception:
        logger.exception(
            "Ready App parent status synchronization failed for child service=%s",
            service_id,
        )



def _invalidate_service_cache_soft(user_id):
    """Invalidate service list/detail cache without making start/stop fail."""
    try:
        from core.app_cache import invalidate_user_services
        invalidate_user_services(user_id)
    except Exception:
        logger.exception("Service cache invalidation failed for user=%s", user_id)


# ---------------------------------------------------------------------------
# Permission helpers (aligned with users.admin_apis Rule system)
# ---------------------------------------------------------------------------

from .common import (
    _get_service_for_user,
    _get_service_for_user_or_share,
    _parse_deploy_config,
    _resolve_platform,
)
from .sharing import record_share_event

@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def service_logs_apiview(request, pk):
    """Historical runtime logs from the persistent log store only."""
    try:
        service, share = _get_service_for_user_or_share(
            request, pk, action="can_view_logs", for_update=False
        )
    except PermissionError as pe:
        return Response(
            {"result": "error", "detail": str(pe)},
            status=status.HTTP_403_FORBIDDEN,
        )
    except Service.DoesNotExist:
        return Response(
            {"result": "error", "detail": _("Service not found.")},
            status=status.HTTP_404_NOT_FOUND,
        )

    from logs.query import query_logs
    from logs.exceptions import ExpiredCursorError
    from logs.policy import resolve
    from logs.usage import get_usage
    from django.utils.dateparse import parse_datetime

    from_ts = parse_datetime(request.query_params.get("from") or "") if request.query_params.get("from") else None
    to_ts = parse_datetime(request.query_params.get("to") or "") if request.query_params.get("to") else None
    try:
        data = query_logs(
            service.pk,
            from_ts=from_ts,
            to_ts=to_ts,
            level=(request.query_params.get("level") or "").strip(),
            stream=(request.query_params.get("stream") or "").strip(),
            q=(request.query_params.get("q") or "").strip(),
            cursor=request.query_params.get("cursor") or None,
            direction=(request.query_params.get("direction") or "older").strip(),
            limit=int(request.query_params.get("limit") or 100),
        )
    except ExpiredCursorError as exc:
        return Response(
            {"result": "error", "code": "EXPIRED_CURSOR", "detail": str(exc)},
            status=status.HTTP_409_CONFLICT,
        )
    except Exception as exc:
        return Response(
            {"result": "error", "detail": str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    policy = resolve(service)
    usage = get_usage(service.pk)
    lines = [e.get("message") or "" for e in data.get("events") or []]
    return Response(
        {
            "result": "success",
            "source": "persistent",
            "logs": lines,
            "events": data.get("events") or [],
            "next_cursor": data.get("next_cursor"),
            "prev_cursor": data.get("prev_cursor"),
            "has_more_older": data.get("has_more_older"),
            "has_more_newer": data.get("has_more_newer"),
            "policy": {
                "mode": policy.mode,
                "retention_days": policy.retention_days,
                "storage_quota_bytes": policy.storage_quota_bytes,
                "persistent_enabled": policy.persistent_enabled,
                "realtime_enabled": policy.realtime_enabled,
                "quota_behavior": policy.quota_behavior,
                "history_available": policy.persistent_enabled,
            },
            "usage": usage,
        },
        status=status.HTTP_200_OK,
    )



@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def service_logs_export_apiview(request, pk):
    try:
        service, share = _get_service_for_user_or_share(
            request, pk, action="can_view_logs", for_update=False
        )
    except PermissionError as pe:
        return Response({"result": "error", "detail": str(pe)}, status=status.HTTP_403_FORBIDDEN)
    except Service.DoesNotExist:
        return Response({"result": "error", "detail": _("Service not found.")}, status=status.HTTP_404_NOT_FOUND)
    from logs.query import export_logs
    from django.utils.dateparse import parse_datetime
    from django.http import HttpResponse

    fmt = (request.query_params.get("format") or "txt").lower()
    from_ts = parse_datetime(request.query_params.get("from") or "") if request.query_params.get("from") else None
    to_ts = parse_datetime(request.query_params.get("to") or "") if request.query_params.get("to") else None
    ctype, body = export_logs(
        service.pk,
        fmt=fmt if fmt in {"txt", "jsonl"} else "txt",
        from_ts=from_ts,
        to_ts=to_ts,
        level=(request.query_params.get("level") or "").strip(),
        stream=(request.query_params.get("stream") or "").strip(),
        q=(request.query_params.get("q") or "").strip(),
        limit=int(request.query_params.get("limit") or 5000),
    )
    resp = HttpResponse(body, content_type=ctype)
    resp["Content-Disposition"] = f'attachment; filename="service-{service.pk}-logs.{"jsonl" if fmt=="jsonl" else "txt"}"'
    return resp


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def start_service_apiview(request):
    """
    Queue a service start (or rebuild).

    Body parameters
    ---------------
    service_id    : UUID  — required
    force_rebuild : bool  — optional (default false)
    """
    service_id = request.data.get("service_id", "")
    force_rebuild = str(request.data.get("force_rebuild", "")).lower() in (
        "1",
        "true",
        "yes",
    )
    share = None
    task_id = None

    try:
        with transaction.atomic():
            action = "can_rebuild" if force_rebuild else "can_start"
            try:
                service_item, share = _get_service_for_user_or_share(
                    request, service_id, action=action, for_update=True
                )
            except PermissionError as pe:
                return Response(
                    {"result": "error", "detail": str(pe)},
                    status=status.HTTP_403_FORBIDDEN,
                )
            except Service.DoesNotExist:
                return Response(
                    {"result": "error", "detail": _("Service not found.")},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Older stop workers could mark a Service FAILED even when its
            # Swarm tasks kept running. Reconcile those legacy projections
            # before deciding to create another deployment.
            if (
                not force_rebuild
                and swarm_enabled()
                and service_item.status in (
                    SERVICE_STATUS_CHOICES.RUNNING,
                    SERVICE_STATUS_CHOICES.SUCCEEDED,
                    SERVICE_STATUS_CHOICES.FAILED,
                    SERVICE_STATUS_CHOICES.STOPPED,
                )
            ):
                try:
                    observed = SwarmRuntime().inspect_service(
                        service_item.get_docker_service_name()
                    )
                except Exception:
                    logger.exception(
                        "Could not verify Swarm runtime before starting service %s; refusing a potentially duplicate deployment.",
                        service_item.pk,
                    )
                    return Response(
                        {
                            "result": "error",
                            "code": "RUNTIME_STATE_UNKNOWN",
                            "detail": _(
                                "The current runtime state could not be verified. No new deployment was queued; please retry."
                            ),
                        },
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )

                if observed is not None and observed.replicas_running > 0:
                    if observed.replicas_desired <= 0:
                        return Response(
                            {
                                "result": "error",
                                "code": "RUNTIME_STOP_DRAINING",
                                "detail": _(
                                    "The previous stop is still being applied by Swarm. No new deployment was queued; retry after the runtime state settles."
                                ),
                                "status": "stopping",
                            },
                            status=status.HTTP_409_CONFLICT,
                        )

                    from services.lifecycle import bump_lifecycle
                    from deployments.core.state.manager import StateManager

                    lifecycle_generation = int(service_item.lifecycle_generation or 0)
                    if (
                        str(service_item.desired_state or "").lower() != "running"
                        or service_item.status != SERVICE_STATUS_CHOICES.RUNNING
                    ):
                        lifecycle_generation = bump_lifecycle(
                            service_item.pk, desired_state="running"
                        )
                        if service_item.status != SERVICE_STATUS_CHOICES.RUNNING:
                            StateManager.transition_service(
                                service_item.pk,
                                SERVICE_STATUS_CHOICES.RUNNING,
                                update_fields={"desired_state": "running"},
                                allow_runtime_reconciliation=True,
                            )
                        else:
                            service_item.desired_state = "running"
                            service_item.lifecycle_generation = lifecycle_generation
                            service_item.save(
                                update_fields=["desired_state", "lifecycle_generation"]
                            )
                        transaction.on_commit(
                            lambda: _invalidate_service_cache_soft(request.user.pk)
                        )
                    return Response(
                        {
                            "result": "success",
                            "detail": _(
                                "The service is already running. Its status was synchronized; no new deployment was created."
                            ),
                            "status": "running",
                            "running": True,
                            "task_id": None,
                            "replicas_desired": observed.replicas_desired,
                            "replicas_running": observed.replicas_running,
                        },
                        status=status.HTTP_200_OK,
                    )

            # A start on an already-running legacy Docker service is idempotent.
            # Swarm services are only considered running after runtime inspection.
            # reset the successful Deploy row or enqueue another deployment.
            if (
                not force_rebuild
                and not swarm_enabled()
                and service_item.status in (
                    SERVICE_STATUS_CHOICES.RUNNING,
                    SERVICE_STATUS_CHOICES.SUCCEEDED,
                )
            ):
                if str(service_item.desired_state or "").lower() != "running":
                    from services.lifecycle import bump_lifecycle

                    lifecycle_generation = bump_lifecycle(
                        service_item.pk, desired_state="running"
                    )
                    service_item.desired_state = "running"
                    service_item.lifecycle_generation = lifecycle_generation
                    service_item.save(
                        update_fields=["desired_state", "lifecycle_generation"]
                    )
                    transaction.on_commit(
                        lambda: _invalidate_service_cache_soft(request.user.pk)
                    )
                return Response(
                    {
                        "result": "success",
                        "detail": _("Service is already running."),
                        "status": "running",
                        "running": True,
                        "task_id": None,
                    },
                    status=status.HTTP_200_OK,
                )

            deploy_item = get_active_deploy(service_item)
            if deploy_item is None:
                # Compatibility bridge for services created before the
                # ServiceRevision migration. The selected legacy deployment
                # is materialized into an immutable revision on first start.
                from services.revisioning import ensure_active_revision_for_service

                ensure_active_revision_for_service(service_item)
                service_item.refresh_from_db(fields=["active_revision"])
                deploy_item = get_active_deploy(service_item)

            if deploy_item is None:
                return Response(
                    {
                        "result": "error",
                        "detail": _(
                            "This service has no deployable revision. "
                            "Create or select a deployment first."
                        ),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if service_item.status in (
                SERVICE_STATUS_CHOICES.QUEUED,
                SERVICE_STATUS_CHOICES.DEPLOYING,
                SERVICE_STATUS_CHOICES.STOPPING,
            ):
                return Response(
                    {
                        "result": "error",
                        "detail": _(
                            "You can't start service in (queued, deploying, stopping) modes."
                        ),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            if getattr(deploy_item, "service_id", None) and not getattr(
                getattr(deploy_item, "service", None), "plan_id", None
            ):
                deploy_item = (
                    Deploy.objects.select_related("service", "service__plan").get(
                        pk=deploy_item.pk
                    )
                )
            else:
                try:
                    deploy_item = (
                        Deploy.objects.select_related("service", "service__plan").get(
                            pk=deploy_item.pk
                        )
                    )
                except Deploy.DoesNotExist:
                    pass

            platform = _resolve_platform(deploy_item)
            is_db = platform in DB_PLATFORMS

            cfg = _parse_deploy_config(getattr(deploy_item, "config", None))
            if cfg.get("platform") != platform:
                cfg["platform"] = platform
                Deploy.objects.filter(pk=deploy_item.pk).update(config=cfg)

            if force_rebuild:

                from deploy.daily_limits import assert_daily_deploy_allowed
                ok_lim, lim_msg, used, limit = assert_daily_deploy_allowed(service_item, request.user)
                if not ok_lim:
                    return Response(
                        {"result": "error", "detail": lim_msg, "used": used, "limit": limit},
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )
                container_name = service_item.get_docker_service_name()
                try:
                    if is_db:
                        DBDeployer().remove(container_name)
                    elif swarm_enabled():
                        SwarmRuntime().remove_service_group(str(service_item.pk))
                    else:
                        OrchestratorDeploy.remove_all(container_name)
                except Exception as exc:
                    logger.warning(
                        "start_service force_rebuild teardown warning "
                        "for service '%s': %s",
                        service_id,
                        exc,
                    )

            from services.lifecycle import bump_lifecycle
            lifecycle_generation = bump_lifecycle(service_item.pk, desired_state="running")
            service_item.desired_state = "running"
            service_item.lifecycle_generation = lifecycle_generation

            task_id = make_uuid4()
            service_item.status = SERVICE_STATUS_CHOICES.QUEUED
            service_item.deploy_started = timezone.now()
            service_item.task_id = task_id
            service_item.save(update_fields=[
                "status", "deploy_started", "task_id",
                "desired_state", "lifecycle_generation",
            ])
            transaction.on_commit(
                lambda sid=service_item.pk: _sync_ready_app_parent_status(sid)
            )

            Deploy.objects.filter(pk=deploy_item.pk).update(
                status="pending",
                stage="queued",
                progress=0,
                status_message="Rebuild queued."
                if force_rebuild
                else "Deployment queued.",
                error_message="",
                cancel_requested=False,
                expected_lifecycle_generation=lifecycle_generation,
                expected_active_revision_id=str(service_item.active_revision_id or ""),
                worker_recovery_attempts=0,
            )

            def _enqueue_after_commit() -> None:
                # Publish only after the transaction is durable. Celery itself is
                # configured with publish retries; this callback adds a bounded
                # application-level retry for transient Redis connection failures.
                task = run_db_deploy if is_db else start_service
                try:
                    task.apply_async(
                        args=[str(deploy_item.id)],
                        task_id=task_id,
                        retry=True,
                        retry_policy={
                            "max_retries": 5,
                            "interval_start": 0,
                            "interval_step": 0.5,
                            "interval_max": 3,
                        },
                    )
                    logger.info(
                        "Celery task published deploy=%s service=%s task_id=%s broker=%s",
                        deploy_item.id, service_id, task_id,
                        getattr(settings, "CELERY_BROKER_URL", "unknown"),
                    )
                except Exception:
                    logger.exception(
                        "Celery enqueue failed after commit for deploy=%s service=%s; "
                        "leaving operation queued for monitor retry",
                        deploy_item.id, service_id,
                    )

            transaction.on_commit(_enqueue_after_commit)
            transaction.on_commit(
                lambda: _invalidate_service_cache_soft(request.user.pk)
            )

    except Service.DoesNotExist:
        return Response(
            {
                "result": "error",
                "detail": _(f"Service with this ID:{service_id} not found."),
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as exc:
        # Broker/network/database failures from transaction.on_commit must not
        # become opaque HTTP 500s. The DB changes are rolled back while the
        # client receives an actionable, sanitized response.
        logger.exception("Failed to queue service start for %s", service_id)
        return Response(
            {
                "result": "error",
                "detail": _("Could not queue the service operation."),
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Record share activity when the actor is a share recipient
    try:
        if share is not None:
            record_share_event(
                share,
                actor=request.user,
                action="deploy" if force_rebuild else "start",
                metadata={"force_rebuild": force_rebuild, "task_id": str(task_id)},
            )
    except Exception:
        logger.exception("Failed to record share event for start service=%s", service_id)

    action_word = "Rebuild" if force_rebuild else "Start"
    return Response(
        {
            "result": "success",
            "detail": _(f"{action_word} queued."),
            "task_id": task_id,
        },
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def stop_service_apiview(request):
    service_id = request.data.get("service_id", "")
    share = None

    try:
        with transaction.atomic():
            try:
                service_item, share = _get_service_for_user_or_share(
                    request, service_id, action="can_stop", for_update=True
                )
            except PermissionError as pe:
                return Response(
                    {"result": "error", "detail": str(pe)},
                    status=status.HTTP_403_FORBIDDEN,
                )
            except Service.DoesNotExist:
                return Response(
                    {"result": "error", "detail": _("Service not found.")},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if (
                service_item.status == SERVICE_STATUS_CHOICES.STOPPING
                and str(service_item.desired_state or "").lower() == "stopped"
            ):
                return Response(
                    {
                        "result": "success",
                        "detail": _("Service stop is already in progress."),
                        "status": "stopping",
                        "task_id": str(service_item.task_id or ""),
                    },
                    status=status.HTTP_202_ACCEPTED,
                )
            if (
                service_item.status == SERVICE_STATUS_CHOICES.STOPPED
                and str(service_item.desired_state or "").lower() == "stopped"
            ):
                return Response(
                    {
                        "result": "success",
                        "detail": _("Service is already stopped."),
                        "status": "stopped",
                        "task_id": None,
                    },
                    status=status.HTTP_200_OK,
                )
            if service_item.status in (
                SERVICE_STATUS_CHOICES.QUEUED,
                SERVICE_STATUS_CHOICES.DEPLOYING,
                SERVICE_STATUS_CHOICES.STOPPING,
            ):
                return Response(
                    {
                        "result": "error",
                        "detail": _(
                            "You can't stop service in (queued, deploying, stopping) modes."
                        ),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            custom_task_id = make_uuid4()

            # Fence the stop intent before the Celery worker runs. The stop worker
            # may wait behind an in-flight deployment's advisory lock.
            from services.lifecycle import bump_lifecycle
            lifecycle_generation = bump_lifecycle(service_item.pk, desired_state="stopped")
            service_item.desired_state = "stopped"
            service_item.lifecycle_generation = lifecycle_generation

            service_item.status = SERVICE_STATUS_CHOICES.STOPPING
            service_item.task_id = custom_task_id
            service_item.deploy_started = timezone.now()
            service_item.save(
                update_fields=[
                    "status", "task_id", "deploy_started",
                    "desired_state", "lifecycle_generation",
                ]
            )
            transaction.on_commit(
                lambda sid=service_item.pk: _sync_ready_app_parent_status(sid)
            )

            transaction.on_commit(
                lambda: stop_service.apply_async(
                    args=[str(service_id)],
                    kwargs={
                        "expected_lifecycle_generation": lifecycle_generation,
                    },
                    task_id=custom_task_id,
                )
            )

            if share is not None:
                try:
                    record_share_event(
                        share,
                        actor=request.user,
                        action="stop",
                        metadata={"task_id": str(custom_task_id)},
                    )
                except Exception:
                    logger.exception(
                        "Failed to record share event for stop service=%s", service_id
                    )

    except Service.DoesNotExist:
        return Response(
            {
                "result": "error",
                "detail": _(f"Service with this ID:{service_id} not found."),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {"result": "success", "detail": _("Service stop requested.")},
        status=status.HTTP_202_ACCEPTED,
    )


def _force_cancel_runtime_cleanup(
    service,
    *,
    container_name: str,
    deploy=None,
    ownership_check=None,
) -> dict:
    """Remove only journaled runtime resources exclusively owned by a deploy."""
    report = {
        "runtime": "docker-swarm" if swarm_enabled() else "docker",
        "target_deploy": getattr(deploy, "pk", None),
        "container": None,
        "services": [],
        "images": [],
        "intermediate_containers": [],
        "errors": [],
    }
    deploy_id = str(getattr(deploy, "pk", "")) if deploy is not None else ""

    def assert_owner() -> None:
        if callable(ownership_check) and not ownership_check():
            raise StaleDeploymentWorkerError(
                "Force-cancel cleanup no longer owns the current lifecycle generation.",
                details={"service_id": str(service.pk), "deploy_id": deploy_id},
            )

    assert_owner()

    # A stable Swarm service may have been updated in place. When a previous
    # revision remains authoritative, the service is shared runtime state and
    # must be restored by desired-state reconciliation instead of deleted.
    if getattr(service, "active_revision_id", None):
        report["preserved_for_active_revision"] = str(service.active_revision_id)
        return report

    if swarm_enabled():
        try:
            runtime = SwarmRuntime()
            from deploy.models import DeploymentResource
            resources = DeploymentResource.objects.filter(
                deployment_id=getattr(deploy, "pk", None),
                kind="runtime_service",
                owned=True,
            ).exclude(state="retired")
            for resource in resources:
                assert_owner()
                name = str(resource.name or "").strip()
                if not name:
                    continue
                try:
                    try:
                        docker_service = runtime.client.services.get(name)
                    except DockerNotFound:
                        report["services"].append({"name": name, "result": "absent"})
                        resource.state = "retired"
                        resource.retired_at = timezone.now()
                        resource.last_error = ""
                        resource.save(update_fields=["state", "retired_at", "last_error", "updated_at"])
                        continue
                    labels = ((docker_service.attrs or {}).get("Spec") or {}).get("Labels") or {}
                    owner = str(labels.get("passdeployer.deployment") or "")
                    service_owner = str(labels.get("passdeployer.service") or "")
                    if owner != deploy_id or service_owner != str(service.pk):
                        report["services"].append({"name": name, "result": "not_owned"})
                        report["errors"].append(
                            f"swarm service {name}: ownership labels do not match the cancelled deployment."
                        )
                        continue
                    assert_owner()
                    runtime.remove(name)
                    report["services"].append({"name": name, "result": "removed"})
                    resource.state = "retired"
                    resource.retired_at = timezone.now()
                    resource.last_error = ""
                    resource.save(update_fields=["state", "retired_at", "last_error", "updated_at"])
                except Exception as exc:
                    if isinstance(exc, StaleDeploymentWorkerError):
                        raise
                    report["errors"].append(f"swarm service {name}: {exc}")
        except Exception as exc:
            if isinstance(exc, StaleDeploymentWorkerError):
                raise
            report["errors"].append(f"swarm runtime: {exc}")
        return report

    assert_owner()
    try:
        client = Client()()
    except Exception as exc:
        report["errors"].append(f"docker client: {exc}")
        return report

    try:
        candidates = client.containers.list(all=True)
        for c in candidates:
            assert_owner()
            labels = dict(getattr(c, "labels", {}) or {})
            cid = str(labels.get("deployment.id") or labels.get("io.passdeployer.deployment") or "")
            if not deploy_id or cid != deploy_id:
                continue
            cname = (getattr(c, "name", "") or "").lstrip("/")
            try:
                assert_owner()
                if getattr(c, "status", "") == "running":
                    c.stop(timeout=5)
                assert_owner()
                c.remove(force=True)
                report["intermediate_containers"].append({"name": cname, "result": "removed"})
            except Exception as exc:
                if isinstance(exc, StaleDeploymentWorkerError):
                    raise
                report["errors"].append(f"container {cname}: {exc}")
    except Exception as exc:
        if isinstance(exc, StaleDeploymentWorkerError):
            raise
        report["errors"].append(f"list containers: {exc}")

    return report


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def force_cancel_deploy_apiview(request):
    """Immediately cancel one active deployment and publish terminal state.

    Body accepts ``deploy_id`` (preferred) or ``service_id`` (legacy).
    The API fences the worker immediately and schedules ownership-checked
    cleanup after the per-service deployment lock becomes available.
    """
    deploy_id = request.data.get("deploy_id")
    service_id = request.data.get("service_id")
    if not deploy_id and not service_id:
        return Response({"result": "error", "detail": _("deploy_id or service_id is required.")}, status=status.HTTP_400_BAD_REQUEST)

    try:
        qs = Deploy.objects.select_related("service", "service__plan", "service__selected_deploy")
        if deploy_id:
            selected = qs.get(pk=deploy_id, service__user=request.user)
            service_item = selected.service
        else:
            service_item = Service.objects.select_related("selected_deploy", "plan").get(id=service_id, user=request.user)
            selected = service_item.selected_deploy
            if selected is None:
                return Response({"result": "error", "detail": _("This service has no selected deployment to cancel.")}, status=status.HTTP_409_CONFLICT)
    except (Deploy.DoesNotExist, Service.DoesNotExist):
        return Response({"result": "error", "detail": _("Deployment or service not found.")}, status=status.HTTP_404_NOT_FOUND)

    # Deploy.status has a smaller, explicit state machine than the legacy
    # Service.status values. Only deployments that can still execute are
    # force-cancellable; queued is a Service state, not a Deploy state.
    active_states = {
        DeploymentStatusChoices.PENDING,
        DeploymentStatusChoices.RUNNING,
    }

    with transaction.atomic():
        # Re-lock the Service and Deploy together so a concurrent rebuild/start
        # cannot make us revoke or mutate a newer execution.
        service_item = Service.objects.select_for_update().get(pk=service_item.pk)
        target_deploy_id = selected.pk if deploy_id else service_item.selected_deploy_id
        if not target_deploy_id:
            return Response(
                {"result": "error", "detail": _("This service has no selected deployment to cancel.")},
                status=status.HTTP_409_CONFLICT,
            )

        locked = Deploy.objects.select_for_update().get(
            pk=target_deploy_id,
            service_id=service_item.pk,
        )
        current = str(locked.status or "").lower()
        if current == DeploymentStatusChoices.CANCELLED:
            return Response(
                {
                    "result": "success",
                    "detail": _("Deployment is already cancelled."),
                    "deploy_id": str(locked.pk),
                },
                status=status.HTTP_200_OK,
            )
        if current not in active_states:
            return Response(
                {
                    "result": "error",
                    "detail": _("Only an active deployment can be force-cancelled."),
                    "status": current,
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Prefer the deployment's authoritative execution owner. The Service
        # task id is retained as a compatibility fallback for older rows.
        task_id = (
            str(locked.execution_task_id or "").strip()
            or str(getattr(service_item, "task_id", "") or "").strip()
            or None
        )
        from deployments.core.state.manager import StateManager
        from services.lifecycle.fencing import bump_lifecycle
        desired_state = "running" if service_item.active_revision_id else "stopped"
        lifecycle_generation = bump_lifecycle(
            service_item.pk,
            desired_state=desired_state,
        )
        StateManager.transition_deploy_system_terminal(
            locked.pk,
            DeploymentStatusChoices.CANCELLED,
            update_fields={
                "cancel_requested": True,
                "stage": "cancelled",
                "progress": 100,
                "status_message": "Deployment force-cancelled by user.",
                "error_message": "Force cancelled by user.",
            },
            event_payload={
                "event_id": str(uuid.uuid4()),
                "trace_id": str(locked.pk),
                "deployment_id": str(locked.pk),
                "service_id": str(locked.service_id),
                "revision_id": str(getattr(locked, "revision_id", "") or ""),
                "task_id": "force-cancel-api",
                "event_type": "deployment.cancelled.warning",
                "stage": "cancelled",
                "level": "warning",
                "message": "Deployment force-cancelled by user.",
                "progress": 100,
                "details": {"controlled_by": "force_cancel_api"},
            },
            expected_execution_task_id=str(locked.execution_task_id or ""),
            expected_lifecycle_generation=lifecycle_generation,
            project_service=False,
        )
        StateManager.transition_service(
            service_item.pk,
            SERVICE_STATUS_CHOICES.RUNNING if service_item.active_revision_id else SERVICE_STATUS_CHOICES.STOPPING,
            update_fields={
                "desired_state": desired_state,
                "task_id": None,
                "deploy_started": None,
            },
            allow_runtime_reconciliation=bool(service_item.active_revision_id),
            expected_lifecycle_generation=lifecycle_generation,
        )
        service_item.refresh_from_db()
        selected = locked

    revoke_result = "not_requested"
    if task_id:
        try:
            from celery import current_app
            current_app.control.revoke(str(task_id), terminate=False)
            revoke_result = "revocation_requested"
        except Exception as exc:
            revoke_result = f"revoke_error: {exc}"
            logger.warning("force_cancel: revoke failed task=%s: %s", task_id, exc)

    cleanup_task_id = None
    try:
        from deployments.celery.tasks import force_cancel_deploy_cleanup
        queued = force_cancel_deploy_cleanup.apply_async(
            args=[str(service_item.pk), int(selected.pk), int(lifecycle_generation)],
            queue="operations",
        )
        cleanup_task_id = str(getattr(queued, "id", "") or "") or None
    except Exception as exc:
        logger.exception("Unable to queue force-cancel cleanup for deploy=%s", selected.pk)
        Deploy.objects.filter(pk=selected.pk, status=DeploymentStatusChoices.CANCELLED).update(
            cleanup_status="pending",
            reconciliation_required=True,
            cleanup_failures=[{"error": str(exc)[:1000]}],
            updated_at=timezone.now(),
        )

    return Response({
        "result": "success" if cleanup_task_id else "partial",
        "detail": _("Deployment cancellation was accepted; owned cleanup is queued and the active release is preserved."),
        "deploy_id": str(selected.pk),
        "task_id": task_id,
        "revoke": revoke_result,
        "cleanup_task_id": cleanup_task_id,
        "lifecycle_generation": lifecycle_generation,
    }, status=status.HTTP_202_ACCEPTED)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def service_status_apiview(request):
    service_id = request.data.get("service_id", "")

    try:
        service_item, _share = _get_service_for_user_or_share(
            request, service_id, action="can_view_metrics", for_update=False
        )
    except PermissionError as pe:
        return Response(
            {
                "result": "error",
                "running": False,
                "cpu": None,
                "ram": None,
                "detail": str(pe),
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    except Service.DoesNotExist:
        return Response(
            {
                "result": "error",
                "running": False,
                "cpu": None,
                "ram": None,
                "metrics_available": False,
                "metrics_reason": "service_not_found",
                "detail": _("Service with the ID not found."),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    name = service_item.get_docker_service_name()
    stats = {}
    try:
        if swarm_enabled():
            stats = SwarmRuntime().service_stats(name)
        else:
            stats = Container(name=name).get_container_stats() or {}

        running = bool(stats.get("running"))
        raw_cpu = stats.get("cpu", stats.get("cpu_percent"))
        raw_ram = stats.get("memory", stats.get("mem_percent", stats.get("ram")))
        cpu = float(raw_cpu) if raw_cpu is not None else None
        ram = float(raw_ram) if raw_ram is not None else None
        detail = _("Service is running.") if running else _("Service is not running.")
        if stats.get("metrics_available") is False:
            detail = _(
                "Service is running, but resource metrics are temporarily unavailable."
            ) if running else _(
                "Service is not running; resource metrics are unavailable."
            )
    except Exception as e:
        logger.exception("service_status error: %s", e)
        running = False
        cpu = None
        ram = None
        stats = {
            "metrics_available": False,
            "metrics_reason": f"service_stats_failed: {e}",
        }
        detail = _("Failed to get service stats.")

    return Response(
        {
            "result": "success",
            "running": running,
            "cpu": cpu,
            "ram": ram,
            "cpu_cores": stats.get("cpu_cores"),
            "cpu_limit_cores": stats.get("cpu_limit_cores"),
            "memory_usage_bytes": stats.get("memory_usage"),
            "memory_limit_bytes": stats.get("memory_limit"),
            "metrics_available": stats.get("metrics_available"),
            "metrics_reason": stats.get("metrics_reason"),
            "detail": detail,
        },
        status=status.HTTP_200_OK,
    )



@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def restart_service_apiview(request):
    """Queue an ordered runtime restart without creating a new revision."""
    service_id = request.data.get("service_id", "")
    share = None
    try:
        with transaction.atomic():
            try:
                service_item, share = _get_service_for_user_or_share(
                    request, service_id, action="can_restart", for_update=True
                )
            except PermissionError as pe:
                return Response({"result": "error", "detail": str(pe)}, status=status.HTTP_403_FORBIDDEN)
            except Service.DoesNotExist:
                return Response({"result": "error", "detail": _("Service not found.")}, status=status.HTTP_404_NOT_FOUND)

            if service_item.status in (
                SERVICE_STATUS_CHOICES.QUEUED,
                SERVICE_STATUS_CHOICES.DEPLOYING,
                SERVICE_STATUS_CHOICES.STOPPING,
            ):
                return Response(
                    {"result": "error", "detail": _("Service is busy; try again later.")},
                    status=status.HTTP_409_CONFLICT,
                )
            if (
                service_item.status == SERVICE_STATUS_CHOICES.STOPPED
                or str(service_item.desired_state or "").lower() == "stopped"
            ):
                return Response(
                    {
                        "result": "error",
                        "code": "RESTART_REQUIRES_RUNNING_SERVICE",
                        "detail": _("A stopped service cannot be restarted. Start it first."),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            from services.lifecycle import bump_lifecycle
            from deployments.core.state.manager import StateManager

            task_id = make_uuid4()
            generation = bump_lifecycle(
                service_item.pk,
                desired_state="running",
            )
            StateManager.transition_service(
                service_item.pk,
                SERVICE_STATUS_CHOICES.QUEUED,
                update_fields={
                    "desired_state": "running",
                    "lifecycle_generation": generation,
                    "task_id": str(task_id),
                    "deploy_started": timezone.now(),
                },
            )

            from deployments.celery.tasks import restart_service as restart_task
            transaction.on_commit(
                lambda: restart_task.apply_async(
                    args=[str(service_id)],
                    kwargs={"expected_lifecycle_generation": generation},
                    task_id=task_id,
                    retry=True,
                    retry_policy={
                        "max_retries": 5,
                        "interval_start": 0,
                        "interval_step": 0.5,
                        "interval_max": 3,
                    },
                )
            )

            if share is not None:
                try:
                    record_share_event(
                        share,
                        actor=request.user,
                        action="restart",
                        metadata={"task_id": str(task_id)},
                    )
                except Exception:
                    logger.exception("restart share event failed")
    except Exception:
        logger.exception("restart failed")
        return Response(
            {"result": "error", "detail": _("Could not queue restart.")},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        {"result": "success", "detail": _("Restart queued."), "task_id": str(task_id)},
        status=status.HTTP_202_ACCEPTED,
    )
