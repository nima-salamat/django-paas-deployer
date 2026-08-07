import functools
import logging
import os
import tarfile
import tempfile
from django.db import transaction
from django.http import FileResponse
from .models import Service, PrivateNetwork, Volume
from deploy.models import Deploy
from django.shortcuts import get_object_or_404
from .serializers import (
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
from rest_framework.decorators import api_view, authentication_classes, permission_classes
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


def _service_is_mutable(service) -> tuple:
    """
    Volume attach/detach/delete is allowed when:
      - service is not busy (running/deploying/queued/stopping)
      - Docker *container* does not exist (image alone does NOT block)

    Returns (ok: bool, reason: str).
    """
    if service is None:
        return True, ""

    status = str(getattr(service, "status", "") or "").lower().strip()
    busy = {
        "queued",
        "deploying",
        "stopping",
        "running",
        "updating...",
        "pending",
    }
    if status in busy:
        return (
            False,
            f"Service is '{status}'. Stop it (and remove the container if needed) before changing volumes.",
        )

    name = service.get_docker_service_name()
    try:
        client = Client()()
        try:
            c = client.containers.get(name)
            # exists → block (even if exited)
            state = ""
            try:
                state = (c.attrs or {}).get("State", {}).get("Status", "") or c.status
            except Exception:
                state = getattr(c, "status", "") or ""
            return (
                False,
                f"Container still exists (status={state or 'unknown'}). "
                "Use 'Remove container & image' first, then change volumes.",
            )
        except DockerNotFound:
            pass
        except Exception as exc:
            # If Docker is unreachable, be conservative but log
            logger.warning("container check for %s: %s", name, exc)
    except Exception as exc:
        logger.warning("docker client for mutability check: %s", exc)

    return True, ""


def _docker_volume_exists(volume) -> bool:
    """True if the underlying Docker volume is present."""
    try:
        _get_docker_volume(volume)
        return True
    except DockerNotFound:
        return False
    except Exception as exc:
        logger.warning("docker volume exists check failed for %s: %s", getattr(volume, "name", "?"), exc)
        return False


def _purge_service_runtime(service) -> dict:
    """Force-stop/remove container and related images. Always best-effort."""
    name = service.get_docker_service_name()
    report = {"container": None, "images": [], "errors": []}
    try:
        client = Client()()
    except Exception as exc:
        report["errors"].append(str(exc))
        return report

    # Container
    try:
        c = client.containers.get(name)
        try:
            c.reload()
            if getattr(c, "status", "") == "running":
                c.stop(timeout=15)
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

    # Images by reference name
    for ref in (name, f"{name}:latest"):
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

    # Update service status if needed
    try:
        from core.global_settings.config import SERVICE_STATUS_CHOICES as SSC

        Service.objects.filter(pk=service.pk).update(status=SSC.STOPPED)
    except Exception:
        try:
            Service.objects.filter(pk=service.pk).update(status="stopped")
        except Exception:
            pass

    return report




def _parse_deploy_config(raw) -> dict:
    """Normalize Deploy.config whether stored as dict or JSON string."""
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        import json

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str) and parsed.strip():
                parsed2 = json.loads(parsed)
                if isinstance(parsed2, dict):
                    return parsed2
        except Exception:
            pass
    return {}


def _resolve_platform(deploy) -> str:
    """config.platform → service.plan.platform → docker."""
    cfg = _parse_deploy_config(getattr(deploy, "config", None))
    p = str(cfg.get("platform") or "").strip().lower()
    if p:
        return p
    service = getattr(deploy, "service", None)
    plan = getattr(service, "plan", None) if service is not None else None
    if plan is not None and getattr(plan, "platform", None):
        return str(plan.platform).strip().lower()
    if service is not None and getattr(service, "plan_id", None):
        try:
            from plans.models import Plan

            plat = (
                Plan.objects.filter(pk=service.plan_id)
                .values_list("platform", flat=True)
                .first()
            )
            if plat:
                return str(plat).strip().lower()
        except Exception:
            logger.exception("Failed to resolve plan.platform")
    return "docker"


class ServiceAdminPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class ServiceViewSet(ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = ServiceAdminPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        query = self.get_queryset()
        q_search_param = request.query_params.get("q_search")
        if q_search_param:
            query = query.filter(name__contains=q_search_param)

        page = self.paginate_queryset(query)
        serializer = GetServiceSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

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
            return Response(
                {"success": _("Service updated.")}, status=status.HTTP_200_OK
            )
        return Response(
            {"error": _("Can not update service."), "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def destroy(self, request, pk=None, *args, **kwargs):
        service = get_object_or_404(self.get_queryset(), pk=pk)
        if service.status in (
            SERVICE_STATUS_CHOICES.QUEUED,
            SERVICE_STATUS_CHOICES.DEPLOYING,
            SERVICE_STATUS_CHOICES.STOPPING,
        ):
            return Response(
                {
                    "result": "error",
                    "detail": _(f"Service is in '{service.status}' mode."),
                },
                status=status.HTTP_409_CONFLICT,
            )

        service.delete()
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
        return super().get_queryset().filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        request.data["user"] = request.user.id
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(
                {"success": _("Private Network created.")},
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
        network = get_object_or_404(self.get_queryset(), pk=pk, user=request.user)
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
        network = get_object_or_404(self.get_queryset(), pk=pk, user=request.user)

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
    Total size of volumes for a service cannot exceed plan.max_storage (GB → MB).
    """

    queryset = Volume.objects.all()
    serializer_class = VolumeSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = ServiceAdminPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superuser:
            return queryset
        return queryset.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        from django.db.models import Q

        queryset = self.get_queryset()
        service_id = request.query_params.get("service")
        unused = request.query_params.get("unused")

        if service_id:
            # Only volumes owned by this service (exclusive)
            queryset = queryset.filter(service_id=service_id)

        if unused is not None and str(unused).lower() in ("1", "true", "yes"):
            # Truly unused = no owning service
            queryset = queryset.filter(service__isnull=True)

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        data = list(serializer.data)

        if service_id:
            for row in data:
                attachments = row.get("service_attachments") or {}
                att = attachments.get(str(service_id)) or {}
                row["bind"] = att.get("bind") or row.get("default_bind") or ""
                row["mode"] = att.get("mode") or row.get("default_mode") or ""

        return self.get_paginated_response(data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                {"error": _("Can not create Volume."), "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service_obj = serializer.validated_data.get("service")
        if service_obj and service_obj.user != request.user:
            return Response(
                {
                    "error": _(
                        "Selected service does not belong to the authenticated user."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Quota already validated in serializer.validate when service is set.
        # If created without service (unused), no quota yet.
        try:
            instance = serializer.save(user=request.user)
        except Exception as exc:
            # Model.clean ValidationError surfaces here
            from django.core.exceptions import ValidationError as DjangoValidationError

            if isinstance(exc, DjangoValidationError):
                msgs = getattr(exc, "message_dict", None) or {
                    "detail": list(getattr(exc, "messages", [str(exc)]))
                }
                return Response(
                    {"error": _("Can not create Volume."), "errors": msgs},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            raise

        # Attach payload for UI (storage remaining after create)
        storage = None
        if instance.service_id:
            try:
                storage = instance.service.storage_quota_summary()
            except Exception:
                storage = None

        return Response(
            {
                "success": _("Volume created."),
                "id": str(instance.pk),
                "storage": storage,
                **self.get_serializer(instance).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, pk=None, *args, **kwargs):
        """
        Rules
        -----
        - Service busy OR container exists → no changes.
        - Docker volume EXISTS → name/size/bind/mode immutable; only service attach/detach.
        - Docker volume MISSING → full metadata edit allowed + attach/detach.
        - Quota checked only on attach (not detach).
        """
        volume = get_object_or_404(self.get_queryset(), pk=pk, user=request.user)
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
        # Even metadata-only edits while attached to a live container are unsafe
        if volume.service_id:
            services_to_check.add(volume.service)

        for svc in services_to_check:
            if svc is None:
                continue
            ok, reason = _service_is_mutable(svc)
            if not ok:
                return Response({"error": reason}, status=status.HTTP_409_CONFLICT)

        # Field edits
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
            # Apply metadata while volume is only a DB row
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

            # If still attached, re-check quota for new size
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

        # Attach / detach
        if touching_service:
            try:
                if target_service is None:
                    # Soft-detach by default (keeps ownership + quota).
                    # Send release=true to hard-release and free quota.
                    release = str(data.get("release", "")).lower() in ("1", "true", "yes")
                    if release and hasattr(volume, "release_from_service"):
                        volume.release_from_service()
                    else:
                        volume.detach_from_service()
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
            },
            status=status.HTTP_200_OK,
        )

    def destroy(self, request, pk=None, *args, **kwargs):
        service = get_object_or_404(self.get_queryset(), pk=pk)
        if service.status in (
            SERVICE_STATUS_CHOICES.QUEUED,
            SERVICE_STATUS_CHOICES.DEPLOYING,
            SERVICE_STATUS_CHOICES.STOPPING,
        ):
            return Response(
                {
                    "result": "error",
                    "detail": _(f"Service is in '{service.status}' mode."),
                },
                status=status.HTTP_409_CONFLICT,
            )

        service.delete()
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
        return super().get_queryset().filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        request.data["user"] = request.user.id
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(
                {"success": _("Private Network created.")},
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
        network = get_object_or_404(self.get_queryset(), pk=pk, user=request.user)
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
        network = get_object_or_404(self.get_queryset(), pk=pk, user=request.user)

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
    Total size of volumes for a service cannot exceed plan.max_storage (GB → MB).
    """

    queryset = Volume.objects.all()
    serializer_class = VolumeSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = ServiceAdminPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superuser:
            return queryset
        return queryset.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        from django.db.models import Q

        queryset = self.get_queryset()
        service_id = request.query_params.get("service")
        unused = request.query_params.get("unused")

        if service_id:
            # Only volumes owned by this service (exclusive)
            queryset = queryset.filter(service_id=service_id)

        if unused is not None and str(unused).lower() in ("1", "true", "yes"):
            # Truly unused = no owning service
            queryset = queryset.filter(service__isnull=True)

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        data = list(serializer.data)

        if service_id:
            for row in data:
                attachments = row.get("service_attachments") or {}
                att = attachments.get(str(service_id)) or {}
                row["bind"] = att.get("bind") or row.get("default_bind") or ""
                row["mode"] = att.get("mode") or row.get("default_mode") or ""

        return self.get_paginated_response(data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(
                {"error": _("Can not create Volume."), "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service_obj = serializer.validated_data.get("service")
        if service_obj and service_obj.user != request.user:
            return Response(
                {
                    "error": _(
                        "Selected service does not belong to the authenticated user."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Quota already validated in serializer.validate when service is set.
        # If created without service (unused), no quota yet.
        try:
            instance = serializer.save(user=request.user)
        except Exception as exc:
            # Model.clean ValidationError surfaces here
            from django.core.exceptions import ValidationError as DjangoValidationError

            if isinstance(exc, DjangoValidationError):
                msgs = getattr(exc, "message_dict", None) or {
                    "detail": list(getattr(exc, "messages", [str(exc)]))
                }
                return Response(
                    {"error": _("Can not create Volume."), "errors": msgs},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            raise

        # Attach payload for UI (storage remaining after create)
        storage = None
        if instance.service_id:
            try:
                storage = instance.service.storage_quota_summary()
            except Exception:
                storage = None

        return Response(
            {
                "success": _("Volume created."),
                "id": str(instance.pk),
                "storage": storage,
                **self.get_serializer(instance).data,
            },
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, pk=None, *args, **kwargs):
        """
        Only attach/detach is allowed (field `service`).
        name / size_mb / default_bind / default_mode are immutable after create.
        Attach/detach require service stopped + no container/image.
        Quota is checked only on attach (not on detach).
        """
        volume = get_object_or_404(self.get_queryset(), pk=pk, user=request.user)
        data = request.data if hasattr(request.data, "get") else {}

        # Reject attempts to edit immutable fields
        forbidden = []
        for field in ("name", "size_mb", "default_bind", "default_mode", "default_mode"):
            if field in data and data.get(field) is not None:
                # allow same value silently; block real changes
                current = getattr(volume, field, None)
                incoming = data.get(field)
                if field == "size_mb":
                    try:
                        if int(incoming) != int(current or 0):
                            forbidden.append(field)
                    except Exception:
                        forbidden.append(field)
                elif str(incoming) != str(current or ""):
                    forbidden.append(field)
        if forbidden:
            return Response(
                {
                    "error": _("Volume fields are immutable after creation."),
                    "errors": {
                        f: _("Cannot edit %(f)s. Delete and recreate the volume.")
                        % {"f": f}
                        for f in forbidden
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "service" not in data:
            return Response(
                {
                    "error": _(
                        "Only attach/detach is supported (send service id or null)."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        service_raw = data.get("service")
        target_service = None
        if service_raw not in (None, "", "null"):
            target_service = get_object_or_404(
                Service.objects.filter(user=request.user), pk=service_raw
            )

        # Mutability: current owner and target must both be safe
        for svc in {volume.service, target_service}:
            if svc is None:
                continue
            ok, reason = _service_is_mutable(svc)
            if not ok:
                return Response(
                    {"error": reason},
                    status=status.HTTP_409_CONFLICT,
                )

        try:
            if target_service is None:
                release = str(data.get("release", "")).lower() in ("1", "true", "yes")
                if release and hasattr(volume, "release_from_service"):
                    volume.release_from_service()
                else:
                    volume.detach_from_service()
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

        storage = None
        volume.refresh_from_db()
        svc = volume.service or target_service
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
            },
            status=status.HTTP_200_OK,
        )

    def destroy(self, request, pk=None, *args, **kwargs):
        volume = get_object_or_404(self.get_queryset(), pk=pk, user=request.user)

        if volume.service_id:
            ok, reason = _service_is_mutable(volume.service)
            if not ok:
                return Response(
                    {"error": reason},
                    status=status.HTTP_409_CONFLICT,
                )

        volume.delete()
        return Response(
            {"success": _("Volume deleted.")}, status=status.HTTP_200_OK
        )


def _docker_volume_names(volume) -> list:
    """Candidate Docker volume names (canonical first)."""
    names = []
    try:
        canonical = volume.get_docker_volume_name()
        if canonical:
            names.append(canonical)
    except Exception:
        pass
    if volume.name and volume.name not in names:
        names.append(volume.name)
    # legacy patterns sometimes used
    try:
        short = f"vol-{volume.id.hex[:8]}-{volume.name}"
        if short not in names:
            names.append(short)
    except Exception:
        pass
    return names


def _get_docker_volume(volume):
    """Resolve the real Docker volume object for a Django Volume row."""
    client = Client()()
    last_err = None
    for name in _docker_volume_names(volume):
        try:
            return client.volumes.get(name), name
        except DockerNotFound as exc:
            last_err = exc
        except Exception as exc:
            last_err = exc
            logger.warning("volumes.get(%s) failed: %s", name, exc)
    if last_err:
        raise last_err
    raise DockerNotFound(f"Volume not found for {volume.name}")


def _get_volume_mountpoint(volume):
    """
    Return host mountpoint if readable; otherwise None.
    Prefer helper-container path when mountpoint is not accessible
    (typical when API runs inside a container).
    """
    docker_vol, docker_name = _get_docker_volume(volume)
    mountpoint = (docker_vol.attrs or {}).get("Mountpoint")
    if mountpoint and os.path.isdir(mountpoint) and os.access(mountpoint, os.R_OK):
        return mountpoint, docker_name
    return None, docker_name


def _list_via_helper_container(docker_name: str):
    """List volume files via short-lived alpine container.

    Emits one JSON object per line (NDJSON) so parsing cannot mix fields:
      {"path":"dir/file.py","type":"file","size":123}
    """
    client = Client()()
    # Pure busybox/ash — no -printf, no python
    script = r"""
set +e
cd /data || exit 1
tmp=/tmp/vol_list.txt
: > "$tmp"
find . -mindepth 1 2>/dev/null | sort | while IFS= read -r p; do
  [ -z "$p" ] && continue
  rel="${p#./}"
  [ -z "$rel" ] && continue
  # escape for JSON string
  esc=$(printf '%s' "$rel" | sed 's/\\/\\\\/g; s/"/\\"/g')
  if [ -d "$p" ]; then
    printf '{"path":"%s","type":"directory","size":0}\n' "$esc" >> "$tmp"
  elif [ -f "$p" ] || [ -L "$p" ]; then
    sz=$(wc -c < "$p" 2>/dev/null | tr -d ' \n')
    case "$sz" in ''|*[!0-9]*) sz=0 ;; esac
    printf '{"path":"%s","type":"file","size":%s}\n' "$esc" "$sz" >> "$tmp"
  fi
done
cat "$tmp"
"""
    container = None
    try:
        container = client.containers.run(
            "alpine:3.20",
            command=["sh", "-c", script],
            volumes={docker_name: {"bind": "/data", "mode": "ro"}},
            detach=True,
            remove=False,
            network_mode="none",
            mem_limit="96m",
        )
        result = container.wait(timeout=90)
        raw = container.logs(stdout=True, stderr=False) or b""
        err = container.logs(stdout=False, stderr=True) or b""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        status_code = result.get("StatusCode", 1) if isinstance(result, dict) else 1

        import json as _json

        files = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # Prefer NDJSON
            if line.startswith("{") and line.endswith("}"):
                try:
                    obj = _json.loads(line)
                    p = str(obj.get("path") or "").strip().lstrip("/").replace("\\", "/")
                    if not p or p in (".", "/"):
                        continue
                    t = str(obj.get("type") or "file").lower()
                    if t in ("d", "dir", "directory"):
                        t = "directory"
                    else:
                        t = "file"
                    try:
                        sz = int(obj.get("size") or 0)
                    except Exception:
                        sz = 0
                    files.append(
                        {
                            "path": p,
                            "type": t,
                            "size": 0 if t == "directory" else max(0, sz),
                            "modified_at": None,
                        }
                    )
                    continue
                except Exception:
                    pass
            # Legacy fallbacks: type|size|path  OR  type\tsize\tmtime\tpath
            if "|" in line and line.count("|") >= 2:
                a, b, c = line.split("|", 2)
                t = a.strip().lower()
                t = "directory" if t.startswith("d") else "file"
                try:
                    sz = int(b)
                except Exception:
                    sz = 0
                p = c.strip().lstrip("/").replace("\\", "/")
                if p:
                    files.append({"path": p, "type": t, "size": 0 if t == "directory" else sz, "modified_at": None})
                continue
            if "\t" in line:
                parts = line.split("\t")
                if len(parts) >= 4:
                    y, size_s, _mtime, p = parts[0], parts[1], parts[2], parts[3]
                elif len(parts) == 3:
                    y, size_s, p = parts[0], parts[1], parts[2]
                else:
                    continue
                p = (p or "").strip().lstrip("/").replace("\\", "/")
                if not p:
                    continue
                t = "directory" if str(y).lower().startswith("d") else "file"
                # handle odd "0\t0\tpath" directory lines from old scripts
                if str(y).strip() == "0":
                    t = "directory"
                    size_s = "0"
                try:
                    sz = int(float(size_s))
                except Exception:
                    sz = 0
                files.append({"path": p, "type": t, "size": 0 if t == "directory" else sz, "modified_at": None})
                continue

        if status_code not in (0, None) and not files:
            raise RuntimeError((err or raw).strip() or f"helper container exit {status_code}")
        return files
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
            try:
                # double-ensure by id if object stale
                cid = getattr(container, "id", None)
                if cid:
                    Client()().containers.get(cid).remove(force=True)
            except Exception:
                pass


def _list_volume_files(root_path):
    files = []
    for base, dirs, filenames in os.walk(root_path):
        rel_base = os.path.relpath(base, root_path)
        if rel_base == ".":
            rel_base = ""
        for dirname in dirs:
            path = os.path.join(rel_base, dirname).replace("\\", "/")
            full = os.path.join(base, dirname)
            try:
                stats = os.stat(full)
                mtime = stats.st_mtime
            except Exception:
                mtime = 0
            files.append(
                {
                    "path": path,
                    "type": "directory",
                    "size": 0,
                    "modified_at": mtime,
                }
            )
        for filename in filenames:
            path = os.path.join(rel_base, filename).replace("\\", "/")
            full = os.path.join(base, filename)
            try:
                stats = os.stat(full)
                size = stats.st_size
                mtime = stats.st_mtime
            except Exception:
                size, mtime = 0, 0
            files.append(
                {
                    "path": path,
                    "type": "file",
                    "size": size,
                    "modified_at": mtime,
                }
            )
    return files


def _archive_via_helper_container(docker_name: str, archive_name: str):
    """Create tar.gz of volume contents via helper container; return host temp path."""
    client = Client()()
    temp_file = tempfile.NamedTemporaryFile(
        prefix="volume_archive_", suffix=".tar.gz", delete=False
    )
    temp_path = temp_file.name
    temp_file.close()

    container = None
    try:
        # Write archive inside the container then copy out
        container = client.containers.run(
            "alpine:3.20",
            command=[
                "sh",
                "-c",
                "cd /data && tar -czf /tmp/vol.tgz . && cat /tmp/vol.tgz",
            ],
            volumes={docker_name: {"bind": "/data", "mode": "ro"}},
            detach=True,
            remove=False,
            network_mode="none",
            mem_limit="256m",
        )
        result = container.wait(timeout=300)
        status_code = result.get("StatusCode", 1) if isinstance(result, dict) else 1
        raw = container.logs(stdout=True, stderr=False) or b""
        if status_code not in (0, None):
            err = container.logs(stdout=False, stderr=True) or b""
            raise RuntimeError(
                err.decode("utf-8", "replace") if isinstance(err, bytes) else str(err)
            )
        if isinstance(raw, str):
            raw = raw.encode("utf-8", "replace")
        with open(temp_path, "wb") as fh:
            fh.write(raw)
        return temp_path
    except Exception:
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        raise
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
            try:
                cid = getattr(container, "id", None)
                if cid:
                    Client()().containers.get(cid).remove(force=True)
            except Exception:
                pass


def _create_volume_archive(root_path, archive_name):
    temp_file = tempfile.NamedTemporaryFile(
        prefix="volume_archive_", suffix=".tar.gz", delete=False
    )
    temp_file.close()
    with tarfile.open(temp_file.name, mode="w:gz") as tar:
        tar.add(root_path, arcname=".")
    return temp_file.name


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def volume_files_apiview(request, pk):
    volume = get_object_or_404(Volume.objects.filter(user=request.user), pk=pk)
    try:
        mountpoint, docker_name = _get_volume_mountpoint(volume)
        if mountpoint:
            files = _list_volume_files(mountpoint)
        else:
            files = _list_via_helper_container(docker_name)
        # sort: directories first, then path
        files.sort(key=lambda x: (0 if x.get("type") == "directory" else 1, x.get("path") or ""))
        return Response(
            {
                "result": "success",
                "docker_name": docker_name,
                "files": files,
                "count": len(files),
            },
            status=status.HTTP_200_OK,
        )
    except DockerNotFound:
        return Response(
            {
                "result": "error",
                "detail": _(
                    "Docker volume not found. It may not have been created yet — "
                    "start/rebuild the service once so the volume is provisioned."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    except ValueError as exc:
        return Response(
            {"result": "error", "detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:
        logger.exception("volume_files failed for %s", pk)
        return Response(
            {
                "result": "error",
                "detail": _("Unable to list volume files: %(err)s")
                % {"err": str(exc)[:300]},
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def volume_download_apiview(request, pk):
    volume = get_object_or_404(Volume.objects.filter(user=request.user), pk=pk)
    archive_path = None
    try:
        mountpoint, docker_name = _get_volume_mountpoint(volume)
        if mountpoint:
            archive_path = _create_volume_archive(mountpoint, volume.name)
        else:
            archive_path = _archive_via_helper_container(docker_name, volume.name)

        response = FileResponse(
            open(archive_path, "rb"),
            as_attachment=True,
            filename=f"{volume.name}.tar.gz",
        )
        response["Content-Length"] = os.path.getsize(archive_path)
        response["Content-Type"] = "application/gzip"

        # Best-effort cleanup after response is closed
        def _cleanup(path=archive_path):
            try:
                os.unlink(path)
            except Exception:
                pass

        try:
            response._resource_closers.append(lambda: _cleanup())  # type: ignore[attr-defined]
        except Exception:
            pass
        return response
    except DockerNotFound:
        if archive_path:
            try:
                os.unlink(archive_path)
            except Exception:
                pass
        return Response(
            {
                "result": "error",
                "detail": _(
                    "Docker volume not found. Start/rebuild the service to provision it."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    except ValueError as exc:
        if archive_path:
            try:
                os.unlink(archive_path)
            except Exception:
                pass
        return Response(
            {"result": "error", "detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:
        if archive_path:
            try:
                os.unlink(archive_path)
            except Exception:
                pass
        logger.exception("volume_download failed for %s", pk)
        return Response(
            {
                "result": "error",
                "detail": _("Unable to create volume archive: %(err)s")
                % {"err": str(exc)[:300]},
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )




@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def purge_service_runtime_apiview(request):
    """
    Force-remove Docker container + image for a service so volumes can be
    attached / detached / deleted. Body: { "service_id": "<uuid>" }
    """
    service_id = request.data.get("service_id", "")
    if not service_id:
        return Response(
            {"result": "error", "detail": _("service_id is required.")},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        service = Service.objects.select_related("plan").get(
            id=service_id, user=request.user
        )
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


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def service_logs_apiview(request, pk):
    service = get_object_or_404(Service.objects.filter(user=request.user), pk=pk)
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
        return Response(
            {"result": "error", "detail": _("Service container not found.")},
            status=status.HTTP_404_NOT_FOUND,
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

    try:
        with transaction.atomic():
            service_item = Service.objects.select_for_update().get(
                id=service_id,
                user=request.user,
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


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def stop_service_apiview(request):
    service_id = request.data.get("service_id", "")

    try:
        with transaction.atomic():
            service_item = Service.objects.select_for_update().get(
                id=service_id, user=request.user
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
