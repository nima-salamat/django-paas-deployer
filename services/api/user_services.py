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


# ---------------------------------------------------------------------------
# Permission helpers (aligned with users.admin_apis Rule system)
# ---------------------------------------------------------------------------

from .common import (
    ServiceAdminPagination,
    _service_is_mutable,
    _docker_volume_exists,
)
from .volume_files import _get_docker_volume

class ServiceViewSet(ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = ServiceAdminPagination

    def get_queryset(self):
        """
        User-facing endpoint: ALWAYS scoped to the authenticated user.

        Staff who also have admin rules still only see *their own* services here.
        Cross-user listing lives under /admin/services/ (see AdminServiceViewSet).
        """
        queryset = super().get_queryset()
        return queryset.filter(user=self.request.user).select_related("user", "network", "plan")

    def list(self, request, *args, **kwargs):
        from core.app_cache import (
            cache_get, cache_set, service_user_list_key,
            SERVICE_USER_TTL, SERVICE_USER_LIMIT,
        )
        params = {
            "q": request.query_params.get("q_search") or request.query_params.get("q") or "",
            "page": request.query_params.get("page") or "1",
            "page_size": request.query_params.get("page_size") or "",
        }
        key = service_user_list_key(request.user.id, params)
        cached = cache_get(key)
        if cached is not None:
            return Response(cached)

        query = self.get_queryset()
        q_search_param = params["q"]
        if q_search_param:
            from django.db.models import Q
            query = query.filter(
                Q(name__icontains=q_search_param)
                | Q(user__username__icontains=q_search_param)
            )

        page = self.paginate_queryset(query)
        serializer = GetServiceSerializer(page if page is not None else query, many=True)
        if page is not None:
            resp = self.get_paginated_response(serializer.data)
            cache_set(key, resp.data, SERVICE_USER_TTL)
            return resp
        data = {"count": len(serializer.data), "results": serializer.data}
        cache_set(key, data, SERVICE_USER_TTL)
        return Response(data)

    def create(self, request, *args, **kwargs):
        request.data["user"] = request.user.id

        network_id = request.data.get("network", None)
        if not network_id or not PrivateNetwork.objects.filter(
            id=network_id, user=request.user
        ).exists():
            return Response(
                {"error": _("You must create a Private Network first.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            try:
                from core.app_cache import invalidate_user_services
                invalidate_user_services(request.user.id)
            except Exception:
                pass
            return Response(
                {
                    "success": _("Service created."),
                    "id": str(instance.pk),
                    "pk": str(instance.pk),
                    "name": instance.name,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )

    def update(self, request, pk=None, *args, **kwargs):
        service = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(service, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            try:
                from core.app_cache import invalidate_user_services
                invalidate_user_services(request.user.id)
            except Exception:
                pass
            return Response(
                {"success": _("Service updated.")}, status=status.HTTP_200_OK
            )
        return Response(
            {"error": _("Can not update service."), "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def destroy(self, request, pk=None, *args, **kwargs):
        """
        Delete service. Blocked while queued/deploying/stopping/running.
        Best-effort purge of container/image before DB delete.
        """
        service = get_object_or_404(self.get_queryset(), pk=pk)
        status_now = str(getattr(service, "status", "") or "").lower().strip()
        blocked = {
            SERVICE_STATUS_CHOICES.QUEUED,
            SERVICE_STATUS_CHOICES.DEPLOYING,
            SERVICE_STATUS_CHOICES.STOPPING,
            SERVICE_STATUS_CHOICES.RUNNING,
            "queued",
            "deploying",
            "stopping",
            "running",
        }
        if status_now in {str(s).lower() for s in blocked} or status_now in blocked:
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

        # Best-effort runtime cleanup so Docker resources are not orphaned
        try:
            _purge_service_runtime(service)
        except Exception as exc:
            logger.warning("purge before service delete failed: %s", exc)

        service.delete()
        try:
            from core.app_cache import invalidate_user_services
            invalidate_user_services(request.user.id)
        except Exception:
            pass
        return Response(
            {"success": _("Service deleted.")}, status=status.HTTP_200_OK
        )

    def retrieve(self, request, *args, **kwargs):
        """Include storage quota summary on service detail."""
        instance = self.get_object()
        data = GetServiceSerializer(instance).data
        return Response(data)


class PrivateNetworkViewSet(ModelViewSet):
    queryset = PrivateNetwork.objects.all()
    serializer_class = PrivateNetworkSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = ServiceAdminPagination

    def get_queryset(self):
        """User-facing: only the authenticated user's networks."""
        qs = super().get_queryset()
        return qs.filter(user=self.request.user).select_related("user")

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        # User-facing create: ALWAYS own network (even for superuser/staff).
        # Cross-user create is only via admin panel APIs.
        owner = request.user
        if hasattr(request.data, "_mutable"):
            request.data._mutable = True
        try:
            data = request.data.copy()
        except Exception:
            data = dict(request.data) if isinstance(request.data, dict) else {}
        data["user"] = owner.id
        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            serializer.save(user=owner)
            return Response(
                {"success": _("Private Network created."), "user": owner.username},
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {
                "error": _("Can not create network."),
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def update(self, request, pk=None, *args, **kwargs):
        network = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(network, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"success": _("Private Network updated.")}, status=status.HTTP_200_OK
            )
        return Response(
            {
                "error": _("Can not update network"),
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def destroy(self, request, pk=None, *args, **kwargs):
        network = get_object_or_404(self.get_queryset(), pk=pk)

        if Service.objects.filter(network=network).exists():
            return Response(
                {
                    "result": "error",
                    "detail": _("Cannot delete network with active services."),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        network.delete()
        return Response(
            {"success": _("Private Network deleted.")},
            status=status.HTTP_200_OK,
        )



class VolumeViewSet(ModelViewSet):
    """
    Volumes are exclusive to one service.

    Storage quota rules (aligned with managed platforms like Railway / Render / Fly):
      - Every volume that still has service FK ownership counts toward plan.max_storage,
        whether currently mounted (attached) or soft-detached.
      - Only hard-release (service=None) or permanent delete frees quota.
      - Soft-detach keeps ownership so quota cannot be bypassed by detach + re-create.

    Mutability rules:
      - Attach / detach / delete-while-mounted require the service to be idle
        (not queued/deploying/running/stopping) AND no Docker container for the service.
      - Metadata edit (name/size/bind/mode) additionally requires the Docker volume
        itself to not exist yet (not provisioned). After first provision, metadata is locked.
      - Soft-detached or orphan volumes may be deleted at any time (no runtime lock).
    """

    queryset = Volume.objects.all()
    serializer_class = VolumeSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = ServiceAdminPagination

    def get_queryset(self):
        """User-facing: only the authenticated user's volumes."""
        queryset = super().get_queryset()
        return queryset.filter(user=self.request.user).select_related("user", "service")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        service_id = request.query_params.get("service")
        unused = request.query_params.get("unused")

        if service_id:
            # Exclusive ownership: only volumes owned by this service
            queryset = queryset.filter(service_id=service_id)

        if unused is not None and str(unused).lower() in ("1", "true", "yes"):
            queryset = queryset.filter(service__isnull=True)

        page = self.paginate_queryset(queryset)
        # Keep model instances so is_mounted is computed from DB, not serializer quirks
        if page is not None:
            instances = list(page)
        else:
            instances = list(queryset)
        serializer = self.get_serializer(instances, many=True)
        data = list(serializer.data)

        for instance, row in zip(instances, data):
            sid = str(service_id) if service_id else str(instance.service_id or "")
            atts = instance.service_attachments or {}
            att = atts.get(sid) or {}
            row["bind"] = att.get("bind") or row.get("default_bind") or instance.default_bind or ""
            row["mode"] = att.get("mode") or row.get("default_mode") or instance.default_mode or ""
            # Authoritative mount flag from DB row
            try:
                row["is_mounted"] = bool(instance.is_mounted_on_service())
            except Exception:
                row["is_mounted"] = bool(att)
            row["service_attachments"] = atts
            row["service"] = str(instance.service_id) if instance.service_id else None

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    def create(self, request, *args, **kwargs):
        owner = request.user

        try:
            serializer = self.get_serializer(
                data=request.data,
                context={"request": request},
            )

            # Catch unexpected validation/database errors too.
            if not serializer.is_valid():
                return Response(
                    {
                        "error": _("Can not create Volume."),
                        "errors": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            service_obj = serializer.validated_data.get("service")

            # User-facing: volume must belong to the authenticated user.
            if service_obj is not None and service_obj.user_id != owner.id:
                return Response(
                    {
                        "error": _(
                            "Selected service does not belong to the authenticated user."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Service must be mutable when volume is created attached to it.
            if service_obj is not None:
                ok, reason = _service_is_mutable(service_obj)
                if not ok:
                    return Response(
                        {"error": reason},
                        status=status.HTTP_409_CONFLICT,
                    )

            # Save inside a transaction so a failed create cannot leave
            # a partially-written DB row.
            from django.db import transaction

            with transaction.atomic():
                instance = serializer.save(user=owner)

            # Calculate quota only after the object has been committed.
            storage = None
            if instance.service_id:
                try:
                    storage = instance.service.storage_quota_summary()
                except Exception:
                    logger.exception(
                        "Failed to calculate storage summary for volume %s",
                        instance.pk,
                    )

            data = self.get_serializer(instance).data

            return Response(
                {
                    "success": _("Volume created."),
                    "id": str(instance.pk),
                    "storage": storage,
                    **data,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as exc:
            # Never allow the API to silently turn a volume-create failure
            # into an opaque HTTP 500.
            logger.exception(
                "Volume creation failed. user=%s payload=%s",
                getattr(owner, "pk", None),
                dict(request.data),
            )

            return Response(
                {
                    "error": _("Can not create Volume."),
                    "detail": str(exc)[:500],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    def update(self, request, pk=None, *args, **kwargs):
        """
        Rules
        -----
        - Service busy OR container exists → no attach/detach/metadata change.
        - Docker volume EXISTS → name/size/bind/mode immutable; only attach/detach.
        - Docker volume MISSING → full metadata edit allowed (+ attach/detach if mutable).
        - Quota: sum of ALL owned volumes (mounted + soft-detached) vs plan limit.
          Checked on create, size change, and attach. Soft-detach does NOT free quota.
        """
        volume = get_object_or_404(self.get_queryset(), pk=pk)
        data = dict(request.data) if hasattr(request.data, "keys") else {}

        docker_exists = _docker_volume_exists(volume)

        service_raw = data.get("service", "__omit__")
        target_service = None
        touching_service = service_raw != "__omit__"
        if touching_service and service_raw not in (None, "", "null"):
            target_service = get_object_or_404(
                Service.objects.filter(user=request.user), pk=service_raw
            )

        # Mutability for any change tied to a service (current owner or target)
        services_to_check = set()
        if volume.service_id:
            services_to_check.add(volume.service)
        if target_service is not None:
            services_to_check.add(target_service)

        for svc in services_to_check:
            if svc is None:
                continue
            ok, reason = _service_is_mutable(svc)
            if not ok:
                return Response({"error": reason}, status=status.HTTP_409_CONFLICT)

        field_keys = ("name", "size_mb", "default_bind", "default_mode")
        wants_field_edit = any(k in data for k in field_keys)

        if wants_field_edit and docker_exists:
            return Response(
                {
                    "error": _(
                        "This volume exists in Docker. Name, size, path and mode "
                        "cannot be edited. Detach, delete, and recreate if you need changes."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if wants_field_edit and not docker_exists:
            if "name" in data and data["name"]:
                volume.name = str(data["name"]).strip()[:32]
            if "size_mb" in data and data["size_mb"] is not None:
                try:
                    volume.size_mb = int(data["size_mb"])
                except (TypeError, ValueError):
                    return Response(
                        {"error": _("size_mb must be a positive integer.")},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if volume.size_mb <= 0:
                    return Response(
                        {"error": _("size_mb must be greater than zero.")},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            if "default_bind" in data:
                volume.default_bind = str(data["default_bind"] or "").strip()
            if "default_mode" in data and data["default_mode"]:
                volume.default_mode = str(data["default_mode"]).strip()

            # Quota re-check against ALL owned volumes when size changes
            if volume.service_id and "size_mb" in data:
                ok, msg = volume.service.can_allocate_storage(
                    volume.size_mb, exclude_volume_id=volume.pk
                )
                if not ok:
                    return Response(
                        {"error": msg, "errors": {"size_mb": msg}},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            try:
                volume.save()
            except Exception as exc:
                from django.core.exceptions import ValidationError as DjangoValidationError

                if isinstance(exc, DjangoValidationError):
                    msgs = getattr(exc, "message_dict", None) or {
                        "detail": list(getattr(exc, "messages", [str(exc)]))
                    }
                    return Response(
                        {"error": _("Can not update Volume"), "errors": msgs},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                raise

        if touching_service:
            try:
                if target_service is None:
                    # Soft-detach by default (keeps ownership + quota).
                    # Send release=true to hard-release and free quota.
                    release = str(data.get("release", "")).lower() in ("1", "true", "yes")
                    if release:
                        volume.release_from_service()
                        Volume.objects.filter(pk=volume.pk).update(
                            service=None, service_attachments={}
                        )
                    else:
                        volume.detach_from_service()
                        Volume.objects.filter(pk=volume.pk).update(
                            service_attachments={}
                        )
                    volume.refresh_from_db()
                else:
                    bind = volume.default_bind or "/data"
                    mode = volume.default_mode or "rw"
                    volume.attach_to_service(target_service, bind=bind, mode=mode)
            except Exception as exc:
                from django.core.exceptions import ValidationError as DjangoValidationError

                if isinstance(exc, DjangoValidationError):
                    msgs = getattr(exc, "message_dict", None) or {
                        "detail": list(getattr(exc, "messages", [str(exc)]))
                    }
                    return Response(
                        {"error": _("Can not update Volume"), "errors": msgs},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                raise

        if not wants_field_edit and not touching_service:
            return Response(
                {
                    "error": _(
                        "Nothing to update. Send service (attach/detach) and/or "
                        "metadata fields when the Docker volume does not exist yet."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        storage = None
        volume.refresh_from_db()
        svc = volume.service
        if svc is not None:
            try:
                storage = svc.storage_quota_summary()
            except Exception:
                storage = None

        return Response(
            {
                "success": _("Volume updated."),
                "storage": storage,
                "service": str(volume.service_id) if volume.service_id else None,
                "docker_exists": _docker_volume_exists(volume),
                "is_mounted": volume.is_mounted_on_service(),
            },
            status=status.HTTP_200_OK,
        )


    @action(detail=True, methods=["post"], url_path="detach")
    def detach(self, request, pk=None):
        """
        Detach volume from its service.

        POST /volume/{id}/detach/
        POST /volume/{id}/detach/?release=1   (or body {"release": true})

        Default = soft-detach:
          service_attachments → {}
          service FK kept (quota still counts)
          is_mounted → false

        release=1 = hard-release:
          service → null, attachments → {}
          quota freed
        """
        volume = get_object_or_404(self.get_queryset(), pk=pk)

        release = str(
            request.query_params.get("release")
            or request.data.get("release")
            or ""
        ).lower() in ("1", "true", "yes")

        # Already free
        if not volume.service_id and not (volume.service_attachments or {}):
            return Response(
                {
                    "success": _("Volume is already detached."),
                    "is_mounted": False,
                    "service": None,
                    "service_attachments": {},
                    "released": True,
                },
                status=status.HTTP_200_OK,
            )

        owner = volume.service
        if owner is not None:
            ok, reason = _service_is_mutable(owner)
            if not ok:
                return Response({"error": reason}, status=status.HTTP_409_CONFLICT)

        if release:
            volume.release_from_service()
            # Force DB row
            Volume.objects.filter(pk=volume.pk).update(
                service=None, service_attachments={}
            )
        else:
            volume.detach_from_service()
            Volume.objects.filter(pk=volume.pk).update(service_attachments={})

        volume.refresh_from_db()

        # Verify write stuck
        if volume.service_attachments:
            Volume.objects.filter(pk=volume.pk).update(service_attachments={})
            volume.refresh_from_db()
        if release and volume.service_id:
            Volume.objects.filter(pk=volume.pk).update(service=None, service_attachments={})
            volume.refresh_from_db()

        storage = None
        svc_for_quota = volume.service or owner
        if svc_for_quota is not None:
            try:
                # Re-fetch after possible hard-release so summary is current
                from ..models import Service as ServiceModel
                svc_obj = ServiceModel.objects.filter(pk=svc_for_quota.pk).first()
                if svc_obj:
                    storage = svc_obj.storage_quota_summary()
            except Exception:
                pass

        mounted = bool(volume.is_mounted_on_service()) if volume.service_id else False

        return Response(
            {
                "success": _(
                    "Volume released (ownership cleared)."
                    if release
                    else "Volume detached (soft — ownership kept, quota still counts)."
                ),
                "service": str(volume.service_id) if volume.service_id else None,
                "is_mounted": mounted,
                "service_attachments": volume.service_attachments or {},
                "released": release,
                "storage": storage,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="attach")
    def attach(self, request, pk=None):
        """
        Attach volume to a service.
        POST /volume/{id}/attach/  body: { "service": "<uuid>" }
        """
        volume = get_object_or_404(self.get_queryset(), pk=pk)
        service_raw = request.data.get("service") or request.data.get("service_id")
        if not service_raw:
            return Response(
                {"error": _("service is required.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target = get_object_or_404(
            Service.objects.filter(user=request.user), pk=service_raw
        )
        ok, reason = _service_is_mutable(target)
        if not ok:
            return Response({"error": reason}, status=status.HTTP_409_CONFLICT)
        if volume.service_id and str(volume.service_id) != str(target.id):
            return Response(
                {"error": _("Volume is owned by another service.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            bind = volume.default_bind or "/data"
            mode = volume.default_mode or "rw"
            volume.attach_to_service(target, bind=bind, mode=mode)
        except Exception as exc:
            from django.core.exceptions import ValidationError as DjangoValidationError
            if isinstance(exc, DjangoValidationError):
                msgs = getattr(exc, "message_dict", None) or {
                    "detail": list(getattr(exc, "messages", [str(exc)]))
                }
                return Response(
                    {"error": _("Can not attach Volume"), "errors": msgs},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            raise
        volume.refresh_from_db()
        storage = None
        try:
            storage = target.storage_quota_summary()
        except Exception:
            pass
        return Response(
            {
                "success": _("Volume attached."),
                "service": str(volume.service_id),
                "is_mounted": volume.is_mounted_on_service(),
                "storage": storage,
            },
            status=status.HTTP_200_OK,
        )


    def destroy(self, request, pk=None, *args, **kwargs):
        """
        Delete volume permanently.

        - Soft-detached or orphan (not mounted): always allowed.
        - Currently mounted on a service: only when that service is mutable
          (idle + no container). Soft-detach first if you only want to unmount.
        """
        volume = get_object_or_404(self.get_queryset(), pk=pk)

        is_mounted = False
        try:
            is_mounted = bool(volume.is_mounted_on_service())
        except Exception:
            is_mounted = bool(volume.service_attachments)

        if is_mounted and volume.service_id:
            ok, reason = _service_is_mutable(volume.service)
            if not ok:
                return Response(
                    {
                        "error": reason
                        or _(
                            "Volume is still mounted. Stop the service and remove "
                            "the container, or detach the volume first."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        # Best-effort: remove Docker volume if present
        try:
            docker_vol = _get_docker_volume(volume)
            try:
                docker_vol.remove(force=True)
            except Exception as exc:
                logger.warning(
                    "docker volume remove failed for %s: %s",
                    getattr(volume, "name", "?"),
                    exc,
                )
        except DockerNotFound:
            pass
        except Exception as exc:
            logger.warning(
                "docker volume lookup on delete for %s: %s",
                getattr(volume, "name", "?"),
                exc,
            )

        owner = volume.service
        volume.delete()

        storage = None
        if owner is not None:
            try:
                storage = owner.storage_quota_summary()
            except Exception:
                storage = None

        return Response(
            {"success": _("Volume deleted."), "storage": storage},
            status=status.HTTP_200_OK,
        )



