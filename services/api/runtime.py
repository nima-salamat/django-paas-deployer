import functools
import logging
import os
import tarfile
import tempfile
from django.db import transaction
from django.conf import settings
from django.http import FileResponse
from ..models import Service, PrivateNetwork, Volume
from deploy.models import Deploy
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
from rest_framework_simplejwt.authentication import JWTAuthentication
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
from deployments.core.manager.container_manager import Container
from deployments.core.manager.client_manager import Client
from docker.errors import NotFound as DockerNotFound


logger = logging.getLogger(__name__)


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
    container_name = service.get_docker_service_name()
    try:
        client = Client()().containers.get(container_name)
        logs = client.logs(tail=200, stdout=True, stderr=True, timestamps=True)
        if isinstance(logs, bytes):
            decoded = logs.decode("utf-8", "replace")
        else:
            decoded = str(logs)
        return Response(
            {"result": "success", "logs": decoded.splitlines()},
            status=status.HTTP_200_OK,
        )
    except DockerNotFound:
        # A stopped/not-yet-deployed service has no container logs. Treat this
        # as an empty log stream so the service page does not surface a noisy
        # HTTP 404 while the deployment is being created or rebuilt.
        return Response(
            {
                "result": "success",
                "logs": [],
                "container_available": False,
                "detail": _("No service container is currently running."),
            },
            status=status.HTTP_200_OK,
        )
    except Exception as exc:
        return Response(
            {"result": "error", "detail": str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


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

            deploy_item = service_item.selected_deploy
            if deploy_item is None:
                return Response(
                    {"result": "error", "detail": _("First select a deploy.")},
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
                container_name = service_item.get_docker_service_name()
                try:
                    if is_db:
                        DBDeployer().remove(container_name)
                    else:
                        OrchestratorDeploy.remove_all(container_name)
                except Exception as exc:
                    logger.warning(
                        "start_service force_rebuild teardown warning "
                        "for service '%s': %s",
                        service_id,
                        exc,
                    )

            task_id = make_uuid4()
            service_item.status = SERVICE_STATUS_CHOICES.QUEUED
            service_item.deploy_started = timezone.now()
            service_item.task_id = task_id
            service_item.save()

            Deploy.objects.filter(pk=deploy_item.pk).update(
                status="pending",
                stage="queued",
                progress=0,
                status_message="Rebuild queued."
                if force_rebuild
                else "Deployment queued.",
                error_message="",
                cancel_requested=False,
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

            service_item.status = SERVICE_STATUS_CHOICES.STOPPING
            service_item.task_id = custom_task_id
            service_item.deploy_started = timezone.now()
            service_item.save(
                update_fields=["status", "task_id", "deploy_started"]
            )

            transaction.on_commit(
                lambda: stop_service.apply_async(
                    args=[str(service_id)], task_id=custom_task_id
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
        {"result": "success", "detail": _("Service stopped.")},
        status=status.HTTP_202_ACCEPTED,
    )


def _force_cancel_runtime_cleanup(service, *, container_name: str) -> dict:
    """
    Best-effort cleanup after a forced deploy cancel.

    - Revoke is done by the caller (needs task_id from DB).
    - Here we only touch Docker: stop/remove the app container, related
      images, and short-lived intermediate/build containers that share the
      service name prefix or managed-by label.
    - Volumes and networks are intentionally preserved.
    """
    report = {
        "container": None,
        "images": [],
        "intermediate_containers": [],
        "errors": [],
    }
    try:
        client = Client()()
    except Exception as exc:
        report["errors"].append(f"docker client: {exc}")
        return report

    # 1) Primary service container
    try:
        c = client.containers.get(container_name)
        try:
            c.reload()
            if getattr(c, "status", "") == "running":
                c.stop(timeout=10)
        except Exception as e:
            report["errors"].append(f"stop: {e}")
        try:
            c.remove(force=True)
            report["container"] = "removed"
        except Exception as e:
            report["errors"].append(f"remove container: {e}")
            report["container"] = "failed"
    except DockerNotFound:
        report["container"] = "absent"
    except Exception as e:
        report["errors"].append(f"container: {e}")
        report["container"] = "error"

    # 2) Intermediate / orphaned build containers
    #    docker build leaves exited helpers; also match name prefix so a
    #    half-created replacement container is not left behind.
    try:
        name_prefix = container_name
        short_id = ""
        try:
            short_id = str(service.id.hex[:8])
        except Exception:
            pass

        candidates = client.containers.list(all=True)
        for c in candidates:
            try:
                cname = (c.name or "").lstrip("/")
                labels = (c.labels or {}) if hasattr(c, "labels") else {}
                attrs_labels = {}
                try:
                    attrs_labels = (c.attrs or {}).get("Config", {}).get("Labels") or {}
                except Exception:
                    pass
                labels = {**attrs_labels, **(labels or {})}

                managed = str(labels.get("managed-by") or "")
                same_name = cname == name_prefix or cname.startswith(name_prefix + "-")
                same_label = (
                    managed == "django-paas-deployer"
                    and short_id
                    and short_id in cname
                )
                # docker build temporary containers often have no useful name
                # but share ancestor of an in-progress image for this service
                if not (same_name or same_label):
                    continue
                if cname == name_prefix and report["container"] == "removed":
                    continue  # already handled
                try:
                    if getattr(c, "status", "") == "running":
                        c.stop(timeout=5)
                except Exception:
                    pass
                try:
                    c.remove(force=True)
                    report["intermediate_containers"].append(
                        {"name": cname, "result": "removed"}
                    )
                except Exception as e:
                    report["intermediate_containers"].append(
                        {"name": cname, "result": f"error: {e}"}
                    )
            except Exception as e:
                report["errors"].append(f"intermediate scan: {e}")
    except Exception as e:
        report["errors"].append(f"list containers: {e}")

    # 3) Images for this service (failed / partial builds)
    for ref in (container_name, f"{container_name}:latest"):
        try:
            client.images.remove(ref, force=True)
            report["images"].append({"ref": ref, "result": "removed"})
        except Exception as e:
            msg = str(e).lower()
            if "no such image" in msg or "not found" in msg:
                report["images"].append({"ref": ref, "result": "absent"})
            else:
                report["images"].append({"ref": ref, "result": f"error: {e}"})
                report["errors"].append(f"image {ref}: {e}")

    # 4) Dangling layers left by interrupted builds (best-effort, never fatal)
    try:
        client.images.prune(filters={"dangling": True})
    except Exception as e:
        report["errors"].append(f"prune dangling: {e}")

    return report


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def force_cancel_deploy_apiview(request):
    """
    Force-cancel an in-progress deploy and clean Docker runtime.

    Body: { "service_id": "<uuid>" }

    Steps (safe, ordered):
      1. Mark cancel_requested on active Deploy rows for this service.
      2. Revoke the Celery task (terminate) so the worker stops ASAP.
      3. Stop/remove the service container + intermediate build containers.
      4. Remove partial images; prune dangling layers.
      5. Set service → stopped, deploy → cancelled.

    Volumes and private networks are NOT deleted.
    """
    service_id = request.data.get("service_id", "")
    if not service_id:
        return Response(
            {"result": "error", "detail": _("service_id is required.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        with transaction.atomic():
            service_item = (
                Service.objects.select_for_update()
                .select_related("selected_deploy")
                .get(id=service_id, user=request.user)
            )
    except Service.DoesNotExist:
        return Response(
            {
                "result": "error",
                "detail": _(f"Service with this ID:{service_id} not found."),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    status_now = str(getattr(service_item, "status", "") or "").lower().strip()
    # Allow force-cancel whenever something is in flight or stuck "running"
    # after a bad deploy; also allow on failed so user can clear leftovers.
    allowed = {
        "queued",
        "deploying",
        "stopping",
        "running",
        "failed",
        "succeeded",
    }
    if status_now and status_now not in allowed and status_now != "stopped":
        # still proceed for unknown statuses — force cancel is intentional
        pass

    task_id = getattr(service_item, "task_id", None)
    container_name = service_item.get_docker_service_name()
    now = timezone.now()

    # --- 1) Signal cancel on all non-terminal deploys for this service ---
    cancelled_deploy_ids: list = []
    try:
        from deploy.models import DeploymentStatusChoices

        terminal = {
            getattr(DeploymentStatusChoices, "SUCCEEDED", "succeeded"),
            getattr(DeploymentStatusChoices, "FAILED", "failed"),
            getattr(DeploymentStatusChoices, "CANCELLED", "cancelled"),
            getattr(DeploymentStatusChoices, "ROLLED_BACK", "rolled_back"),
            "succeeded",
            "failed",
            "cancelled",
            "rolled_back",
        }
        qs = Deploy.objects.filter(service_id=service_item.pk).exclude(
            status__in=list(terminal)
        )
        cancelled_deploy_ids = list(qs.values_list("pk", flat=True))
        update_kwargs = {
            "cancel_requested": True,
            "status": getattr(DeploymentStatusChoices, "CANCELLED", "cancelled"),
            "stage": "cancelled",
            "status_message": "Deployment force-cancelled by user.",
            "completed_at": now,
            "progress": 100,
            "error_message": "Force cancelled by user.",
        }
        if cancelled_deploy_ids:
            Deploy.objects.filter(pk__in=cancelled_deploy_ids).update(**update_kwargs)

        # Always set the flag on the selected deploy so a worker mid-flight sees it
        selected = service_item.selected_deploy
        if selected is not None:
            Deploy.objects.filter(pk=selected.pk).update(cancel_requested=True)
    except Exception as exc:
        logger.exception("force_cancel: deploy flag failed for %s", service_id)
        return Response(
            {
                "result": "error",
                "detail": _("Could not mark deploy as cancelled: %(err)s")
                % {"err": str(exc)[:200]},
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # --- 2) Revoke Celery task (terminate worker) ---
    revoke_result = None
    if task_id:
        try:
            from celery import current_app

            current_app.control.revoke(
                str(task_id), terminate=True, signal="SIGTERM"
            )
            revoke_result = "revoked"
        except Exception as exc:
            logger.warning(
                "force_cancel: revoke failed task=%s: %s", task_id, exc
            )
            revoke_result = f"revoke_error: {exc}"

    # --- 3) Docker cleanup (outside transaction; best-effort) ---
    docker_report = _force_cancel_runtime_cleanup(
        service_item, container_name=container_name
    )

    # --- 4) Service row → stopped ---
    try:
        Service.objects.filter(pk=service_item.pk).update(
            status=SERVICE_STATUS_CHOICES.STOPPED,
            task_id=None,
            deploy_started=None,
        )
    except Exception as exc:
        logger.exception("force_cancel: service update failed")
        docker_report["errors"].append(f"service status: {exc}")

    # Deploy log for audit trail
    try:
        from deploy.models import DeployLog
        from django.conf import settings as dj_settings

        alias = getattr(dj_settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"
        log_deploy_id = (
            cancelled_deploy_ids[0]
            if cancelled_deploy_ids
            else (
                service_item.selected_deploy_id
                if getattr(service_item, "selected_deploy_id", None)
                else None
            )
        )
        if log_deploy_id:
            DeployLog.objects.using(alias).create(
                deploy_id=log_deploy_id,
                service_id=service_item.pk,
                stage="cancelled",
                event_type="deployment.force_cancel",
                level="warning",
                message="Deployment force-cancelled by user; runtime cleaned up.",
                progress=100,
                details={
                    "task_id": task_id,
                    "revoke": revoke_result,
                    "docker": docker_report,
                    "cancelled_deploys": [str(x) for x in cancelled_deploy_ids],
                },
            )
            try:
                from deploy.log_retention import trim_after_write
                trim_after_write(service_item.pk)
            except Exception:
                pass
    except Exception:
        logger.debug("force_cancel: DeployLog write skipped", exc_info=True)

    ok = docker_report.get("container") in ("removed", "absent") and not any(
        str(i.get("result", "")).startswith("error")
        for i in docker_report.get("images", [])
    )
    return Response(
        {
            "result": "success" if ok else "partial",
            "detail": _(
                "Deployment cancelled. Container and intermediate resources cleaned up."
            ),
            "task_id": task_id,
            "revoke": revoke_result,
            "cancelled_deploys": [str(x) for x in cancelled_deploy_ids],
            "report": docker_report,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def service_status_apiview(request):
    service_id = request.data.get("service_id", "")

    try:
        service_item = Service.objects.get(id=service_id, user=request.user)
    except Service.DoesNotExist:
        return Response(
            {
                "result": "error",
                "running": False,
                "cpu": 0,
                "ram": 0,
                "detail": _("Service with the ID not found."),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    name = service_item.get_docker_service_name()
    try:
        container = Container(name=name)
        stats = container.get_container_stats() or {}

        running_raw = stats.get("running", stats.get("is_running", 0))
        if isinstance(running_raw, bool):
            running = running_raw
        elif isinstance(running_raw, (int, float)):
            running = int(running_raw) == 1
        elif isinstance(running_raw, str):
            running = running_raw.strip().lower() in (
                "1",
                "true",
                "yes",
                "running",
            )
        else:
            running = False

        def _as_percent(value):
            try:
                n = float(value if value is not None else 0.0)
            except (TypeError, ValueError):
                return 0.0
            if n < 0:
                n = 0.0
            return round(min(n, 100.0), 2)

        cpu = _as_percent(stats.get("cpu", stats.get("cpu_percent", 0.0)))
        ram = _as_percent(
            stats.get("memory", stats.get("mem_percent", stats.get("ram", 0.0)))
        )

        detail = (
            _("Service is running.") if running else _("Service is not running.")
        )
    except Exception as e:
        logger.exception("service_status error: %s", e)
        running = False
        cpu = 0.0
        ram = 0.0
        detail = _("Failed to get service stats.")

    return Response(
        {
            "result": "success",
            "running": running,
            "cpu": cpu,
            "ram": ram,
            "detail": detail,
        },
        status=status.HTTP_200_OK,
    )



@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def restart_service_apiview(request):
    """
    Restart = stop then start when allowed.
    Requires can_restart (or owner).
    Body: { "service_id": "<uuid>" }
    """
    service_id = request.data.get("service_id", "")
    share = None
    try:
        with transaction.atomic():
            try:
                service_item, share = _get_service_for_user_or_share(
                    request, service_id, action="can_restart", for_update=True
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

            if service_item.status in (
                SERVICE_STATUS_CHOICES.QUEUED,
                SERVICE_STATUS_CHOICES.DEPLOYING,
                SERVICE_STATUS_CHOICES.STOPPING,
            ):
                return Response(
                    {
                        "result": "error",
                        "detail": _("Service is busy; try again later."),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            # Stop path if running
            custom_task_id = make_uuid4()
            if str(service_item.status).lower() == str(SERVICE_STATUS_CHOICES.RUNNING).lower() or str(service_item.status).lower() == "running":
                service_item.status = SERVICE_STATUS_CHOICES.STOPPING
                service_item.task_id = custom_task_id
                service_item.save(update_fields=["status", "task_id"])
                transaction.on_commit(
                    lambda: stop_service.apply_async(
                        args=[str(service_id)], task_id=custom_task_id
                    )
                )
            # Queue start after stop is best-effort; clients may call start separately.
            # For a true restart we also queue deploy if selected_deploy exists.
            deploy_item = service_item.selected_deploy
            if deploy_item is not None:
                start_task_id = make_uuid4()

                def _start_after():
                    try:
                        from deployments.celery.tasks import deploy as start_task
                        start_task.apply_async(args=[str(deploy_item.id)], task_id=start_task_id)
                    except Exception:
                        logger.exception("restart: start enqueue failed")

                transaction.on_commit(_start_after)
                service_item.status = SERVICE_STATUS_CHOICES.QUEUED
                service_item.task_id = start_task_id
                service_item.save(update_fields=["status", "task_id"])

            if share is not None:
                try:
                    record_share_event(
                        share,
                        actor=request.user,
                        action="restart",
                        metadata={},
                    )
                except Exception:
                    logger.exception("restart share event failed")
    except Exception:
        logger.exception("restart failed")
        return Response(
            {"result": "error", "detail": _("Could not restart service.")},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        {"result": "success", "detail": _("Restart queued.")},
        status=status.HTTP_202_ACCEPTED,
    )
