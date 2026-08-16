import functools
import logging
import os
import tarfile
import tempfile
from django.db import transaction
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
from rest_framework.permissions import IsAuthenticated, BasePermission
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


# ---------------------------------------------------------------------------
# Permission helpers (aligned with users.admin_apis Rule system)
# ---------------------------------------------------------------------------

from .common import *  # noqa: F401,F403

class HasServicesViewRule(BasePermission):
    """Superuser OR staff with services.view / services.manage."""

    def has_permission(self, request, view):
        return _can_view_all_services(request.user)


class HasServicesManageRule(BasePermission):
    """Superuser OR staff with services.manage / services.delete."""

    def has_permission(self, request, view):
        return _can_manage_all_services(request.user)


class AdminServiceViewSet(ModelViewSet):
    """
    /admin/services/ — list/inspect all services (or filter by user_id).

    GET requires services.view (or manage).
    Write operations require services.manage.
    """

    queryset = Service.objects.all().select_related("user", "network", "plan")
    serializer_class = ServiceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasServicesViewRule]
    pagination_class = ServiceAdminPagination
    http_method_names = ["get", "post", "patch", "put", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy", "create"):
            return [IsAuthenticated(), HasServicesManageRule()]
        return [IsAuthenticated(), HasServicesViewRule()]

    def get_queryset(self):
        qs = super().get_queryset()
        user_id = (
            self.request.query_params.get("user_id")
            or self.request.query_params.get("user")
        )
        if user_id:
            qs = qs.filter(user_id=user_id)
        q = self.request.query_params.get("q_search") or self.request.query_params.get("q")
        if q:
            from django.db.models import Q

            qs = qs.filter(
                Q(name__icontains=q) | Q(user__username__icontains=q)
            )
        status_val = (self.request.query_params.get("status") or "").strip()
        if status_val:
            qs = qs.filter(status=status_val)
        return qs.order_by("-created_at", "-id")

    def list(self, request, *args, **kwargs):
        """
        Admin service list.

        IMPORTANT: never slice the queryset before paginate_queryset —
        Django Paginator.count() raises / misbehaves on sliced querysets
        and that was the root cause of HTTP 500 on this endpoint.
        """
        # ---- optional cache (soft-fail) ----
        cache_key = None
        try:
            from core.app_cache import cache_get, cache_set, service_admin_list_key, SERVICE_ADMIN_TTL
            params = {
                k: request.query_params.get(k) or ""
                for k in ("q", "q_search", "page", "page_size", "user_id", "status")
            }
            cache_key = service_admin_list_key(params)
            cached = cache_get(cache_key)
            if isinstance(cached, dict) and "results" in cached:
                return Response(cached)
        except Exception:
            logger.exception("admin services: cache read failed")
            cache_key = None

        # ---- DB + pagination (no pre-slice) ----
        try:
            qs = self.get_queryset()
            page = self.paginate_queryset(qs)
            ser = GetServiceSerializer(page if page is not None else qs, many=True)
            data = ser.data
            if page is not None:
                resp = self.get_paginated_response(data)
                body = resp.data
            else:
                body = {"count": len(data), "next": None, "previous": None, "results": data}
                resp = Response(body)
        except Exception:
            logger.exception("admin services: list serialization failed")
            # Minimal fallback so admin panel is not completely blocked
            try:
                rows = []
                for s in Service.objects.select_related("user", "plan").order_by("-created_at")[:20]:
                    rows.append({
                        "id": str(s.pk),
                        "name": s.name,
                        "status": getattr(s, "status", None),
                        "user": getattr(s, "user_id", None),
                        "user_username": getattr(getattr(s, "user", None), "username", None),
                        "plan": str(s.plan_id) if getattr(s, "plan_id", None) else None,
                        "created_at": s.created_at.isoformat() if getattr(s, "created_at", None) else None,
                    })
                body = {"count": len(rows), "next": None, "previous": None, "results": rows}
                resp = Response(body)
            except Exception:
                logger.exception("admin services: fallback list also failed")
                return Response(
                    {"count": 0, "next": None, "previous": None, "results": [], "error": "list failed"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        if cache_key is not None:
            try:
                from core.app_cache import cache_set, SERVICE_ADMIN_TTL
                cache_set(cache_key, body, SERVICE_ADMIN_TTL)
            except Exception:
                logger.exception("admin services: cache write failed")
        return resp

    def create(self, request, *args, **kwargs):
        """
        Create a service owned by a target user (admin impersonation).

        Required payload:
            user_id : int  — the owner of the new service
            name    : str  — unique service name (max 30)
            plan    : int  — Plan.id to bind

        Optional:
            network : int  — PrivateNetwork.id (must belong to the same user)
            read_only : bool
        """
        data = dict(request.data) if hasattr(request.data, "keys") else {}
        owner_id = data.get("user_id") or data.get("user")
        if not owner_id:
            return Response(
                {"error": _("user_id is required.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate owner exists
        try:
            from users.models import User

            owner = User.objects.get(pk=owner_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return Response(
                {"error": _("Target user not found.")},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Validate plan
        plan_id = data.get("plan")
        if not plan_id:
            return Response(
                {"error": _("plan is required.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            from plans.models import Plan

            plan = Plan.objects.get(pk=plan_id)
        except (Plan.DoesNotExist, ValueError, TypeError):
            return Response(
                {"error": _("Plan not found.")},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Optional network — must belong to the target user if provided
        network_id = data.get("network")
        if network_id:
            try:
                PrivateNetwork.objects.get(pk=network_id, user_id=owner.pk)
            except (PrivateNetwork.DoesNotExist, ValueError, TypeError):
                return Response(
                    {"error": _(
                        "Network not found or does not belong to the target user."
                    )},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Build a clean payload
        from django.conf import settings as _dj_settings

        payload = {
            "name": (data.get("name") or "").strip(),
            "user": owner.pk,
            "plan": plan.pk,
            "network": network_id or None,
            "read_only": data.get("read_only", not _dj_settings.DEBUG),
            "status": SERVICE_STATUS_CHOICES.STOPPED.value,
        }
        if not payload["name"] or len(payload["name"]) > 30:
            return Response(
                {"error": _("name is required and must be ≤ 30 characters.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=payload)
        if serializer.is_valid():
            instance = serializer.save()
            try:
                from core.app_cache import invalidate_all_services
                invalidate_all_services()
            except Exception:
                pass
            return Response(
                {
                    "success": _("Service created."),
                    "id": str(instance.pk),
                    "pk": str(instance.pk),
                    "data": GetServiceSerializer(instance).data,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {"error": _("Validation failed."), "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        data = GetServiceSerializer(instance).data
        try:
            data["storage"] = instance.storage_quota_summary()
        except Exception:
            pass
        return Response(data)

    def destroy(self, request, *args, **kwargs):
        if not _can_delete_services(request.user):
            return Response(
                {"result": "error", "detail": _("Missing permission services.delete.")},
                status=status.HTTP_403_FORBIDDEN,
            )
        service = self.get_object()
        status_now = str(getattr(service, "status", "") or "").lower().strip()
        blocked = {"queued", "deploying", "stopping", "running"}
        if status_now in blocked:
            return Response(
                {
                    "result": "error",
                    "detail": _(
                        "Service is '%(s)s'. Stop it and remove the runtime "
                        "before deleting the service."
                    )
                    % {"s": status_now},
                },
                status=status.HTTP_409_CONFLICT,
            )
        try:
            _purge_service_runtime(service)
        except Exception as exc:
            logger.warning("admin purge before service delete failed: %s", exc)
        service.delete()
        return Response(
            {"success": _("Service deleted.")}, status=status.HTTP_200_OK
        )


class AdminPrivateNetworkViewSet(ModelViewSet):
    """ /admin/networks/ — all networks for staff with networks.manage or services.manage """

    queryset = PrivateNetwork.objects.all().select_related("user")
    serializer_class = PrivateNetworkSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasServicesViewRule]
    pagination_class = ServiceAdminPagination
    http_method_names = ["get", "post", "patch", "put", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy", "create"):
            return [IsAuthenticated(), HasServicesManageRule()]
        return [IsAuthenticated(), HasServicesViewRule()]

    def get_queryset(self):
        qs = super().get_queryset()
        user_id = (
            self.request.query_params.get("user_id")
            or self.request.query_params.get("user")
        )
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs.order_by("-id")

    def create(self, request, *args, **kwargs):
        """Create network for a target user (user_id required)."""
        data = dict(request.data) if hasattr(request.data, "keys") else {}
        owner_id = data.get("user_id") or data.get("user")
        if not owner_id:
            return Response(
                {"error": _("user_id is required.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            serializer.save(user_id=owner_id)
            return Response(
                {"success": _("Private Network created."), "data": serializer.data},
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {"error": _("Can not create network."), "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

class AdminVolumeViewSet(ModelViewSet):
    """ /admin/volumes/ — all volumes for staff with volumes.manage or services.manage """

    queryset = Volume.objects.all().select_related("user", "service")
    serializer_class = VolumeSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasServicesViewRule]
    pagination_class = ServiceAdminPagination
    http_method_names = ["get", "post", "patch", "put", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy", "create"):
            return [IsAuthenticated(), HasServicesManageRule()]
        return [IsAuthenticated(), HasServicesViewRule()]

    def get_queryset(self):
        qs = super().get_queryset()
        user_id = (
            self.request.query_params.get("user_id")
            or self.request.query_params.get("user")
        )
        service_id = self.request.query_params.get("service")
        if user_id:
            qs = qs.filter(user_id=user_id)
        if service_id:
            qs = qs.filter(service_id=service_id)
        return qs.order_by("-id")

    def create(self, request, *args, **kwargs):
        """Create volume owned by target user (from service or user_id)."""
        data = dict(request.data) if hasattr(request.data, "keys") else {}
        owner_id = data.get("user_id") or data.get("user")
        service_id = data.get("service")
        service_obj = None
        if service_id:
            try:
                service_obj = Service.objects.get(pk=service_id)
                owner_id = service_obj.user_id
            except Service.DoesNotExist:
                return Response(
                    {"error": _("Service not found.")},
                    status=status.HTTP_404_NOT_FOUND,
                )
        if not owner_id:
            return Response(
                {"error": _("user_id or service is required.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(data=data, context={"request": request})
        if not serializer.is_valid():
            return Response(
                {"error": _("Can not create Volume."), "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if service_obj is not None:
            ok, reason = _service_is_mutable(service_obj)
            if not ok:
                return Response({"error": reason}, status=status.HTTP_409_CONFLICT)
        instance = serializer.save(user_id=owner_id)
        return Response(
            {
                "success": _("Volume created."),
                "id": str(instance.pk),
                **self.get_serializer(instance).data,
            },
            status=status.HTTP_201_CREATED,
        )





def admin_start_service_apiview(request):
    """
    Admin: queue start for any user's service (requires services.manage).

    Body parameters
    ---------------
    service_id    : UUID  — required
    force_rebuild : bool  — optional (default false)
    """
    if not _can_manage_all_services(request.user):
        return Response(
            {"result": "error", "detail": _("Missing permission services.manage.")},
            status=status.HTTP_403_FORBIDDEN,
        )
    service_id = request.data.get("service_id", "")
    force_rebuild = str(request.data.get("force_rebuild", "")).lower() in (
        "1",
        "true",
        "yes",
    )

    try:
        with transaction.atomic():
            service_item = Service.objects.select_for_update().get(id=service_id)
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

            if is_db:
                transaction.on_commit(
                    functools.partial(
                        run_db_deploy.apply_async,
                        args=[str(deploy_item.id)],
                        task_id=task_id,
                    )
                )
            else:
                transaction.on_commit(
                    functools.partial(
                        start_service.apply_async,
                        args=[str(deploy_item.id)],
                        task_id=task_id,
                    )
                )

    except Service.DoesNotExist:
        return Response(
            {
                "result": "error",
                "detail": _(f"Service with this ID:{service_id} not found."),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    action_word = "Rebuild" if force_rebuild else "Start"
    return Response(
        {
            "result": "success",
            "detail": _(f"{action_word} queued."),
            "task_id": task_id,
        },
        status=status.HTTP_202_ACCEPTED,
    )


def admin_stop_service_apiview(request):
    if not _can_manage_all_services(request.user):
        return Response(
            {"result": "error", "detail": _("Missing permission services.manage.")},
            status=status.HTTP_403_FORBIDDEN,
        )
    service_id = request.data.get("service_id", "")

    try:
        with transaction.atomic():
            service_item = Service.objects.select_for_update().get(id=service_id)

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


def admin_purge_service_runtime_apiview(request):
    """
    Force-remove Docker container + image for a service so volumes can be
    attached / detached / deleted. Body: { "service_id": "<uuid>" }
    """
    if not _can_manage_all_services(request.user):
        return Response(
            {"result": "error", "detail": _("Missing permission services.manage.")},
            status=status.HTTP_403_FORBIDDEN,
        )
    service_id = request.data.get("service_id", "")
    if not service_id:
        return Response(
            {"result": "error", "detail": _("service_id is required.")},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        service = Service.objects.select_related("plan").get(pk=service_id)
        service = Service.objects.select_related("plan").get(pk=service.pk)
    except Service.DoesNotExist:
        return Response(
            {"result": "error", "detail": _("Service not found.")},
            status=status.HTTP_404_NOT_FOUND,
        )

    status_now = str(getattr(service, "status", "") or "").lower()
    if status_now in ("queued", "deploying", "stopping"):
        return Response(
            {
                "result": "error",
                "detail": _(
                    "Service is busy (%(s)s). Wait until it is stopped."
                )
                % {"s": status_now},
            },
            status=status.HTTP_409_CONFLICT,
        )

    report = _purge_service_runtime(service)
    ok = report.get("container") in ("removed", "absent") and not any(
        str(i.get("result", "")).startswith("error") for i in report.get("images", [])
    )
    return Response(
        {
            "result": "success" if ok else "partial",
            "detail": _("Container and image cleanup finished."),
            "report": report,
            "mutable": _service_is_mutable(Service.objects.get(pk=service.pk))[0],
        },
        status=status.HTTP_200_OK,
    )


