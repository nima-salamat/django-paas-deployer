# deploy/apis.py
import functools
import logging
import os
import tarfile
import tempfile
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes, action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.viewsets import ModelViewSet

from core.global_settings.config import SERVICE_STATUS_CHOICES
from deployments.celery.tasks import deploy as deploy_task
from deployments.celery.tasks import stop as stop_service
from deployments.core.db_deployer import (
    DB_PLATFORMS,
    DBDeployer,
    MUTABLE_DB_CONFIG_KEYS,
    validate_db_config,
)
from deployments.core.deploy import Deploy as OrchestratorDeploy
from deployments.core.manager.client_manager import Client
from deployments.core.manager.container_manager import Container
from docker.errors import APIError, NotFound as DockerNotFound

from .models import Deploy, DeployLog
from .serializers import DeployLogSerializer, DeploySerializer
from .tasks import run_db_deploy
from services.models import Service
from core.utils import make_uuid4

logger = logging.getLogger(__name__)


def _resolve_platform(deploy) -> str:
    """
    Resolve platform for routing DB vs app deploy tasks.

    Order: deploy.config["platform"] → service.plan.platform → "docker".
    """
    cfg = deploy.config if isinstance(getattr(deploy, "config", None), dict) else {}
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
            logger.exception("Failed to resolve plan.platform for deploy %s", getattr(deploy, "pk", None))

    return "docker"


def _ensure_config_platform(deploy, platform: str) -> dict:
    """Persist platform onto deploy.config when missing so later starts stay correct."""
    cfg = dict(deploy.config) if isinstance(deploy.config, dict) else {}
    if cfg.get("platform") != platform:
        cfg["platform"] = platform
        Deploy.objects.filter(pk=deploy.pk).update(config=cfg)
    return cfg


class DeployPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


def _parse_cursor(value):
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


class DeployViewSet(ModelViewSet):
    queryset = Deploy.objects.all()
    serializer_class = DeploySerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = DeployPagination

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "service", "service__user", "service__plan"
        )
        if self.request.user.is_superuser:
            return qs
        return qs.filter(service__user=self.request.user)

    def list(self, request, *args, **kwargs):
        service_id = request.query_params.get("service_id", "")
        queryset = self.get_queryset().order_by("-created_at")
        if service_id:
            queryset = queryset.filter(service=service_id)

        page = self.paginate_queryset(queryset=queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            service_id = request.data.get("service")
            if not service_id or not Service.objects.filter(id=service_id, user=request.user).exists():
                return Response(
                    {"error": _("Service must belong to the authenticated user.")},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # If client omitted config.platform, inject it from the service plan
        data = request.data
        if hasattr(data, "copy"):
            data = data.copy()
        else:
            data = dict(data)

        service_id = data.get("service")
        raw_config = data.get("config")
        cfg = {}
        if isinstance(raw_config, dict):
            cfg = dict(raw_config)
        elif isinstance(raw_config, str) and raw_config.strip():
            import json
            try:
                parsed = json.loads(raw_config)
                if isinstance(parsed, dict):
                    cfg = parsed
            except Exception:
                pass

        if not cfg.get("platform") and service_id:
            try:
                service = Service.objects.select_related("plan").get(pk=service_id)
                if service.plan_id and getattr(service.plan, "platform", None):
                    cfg["platform"] = str(service.plan.platform).strip().lower()
                    data["config"] = cfg
            except Service.DoesNotExist:
                pass

        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            deploy = serializer.save()
            return Response(
                {"success": _("Deploy created."), "deploy": self.get_serializer(deploy).data},
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {"error": _("Can not deploy."), "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=True, methods=["post"])  # POST /deploy/<pk>/start/
    def start(self, request, pk=None):
        deploy = get_object_or_404(
            self.get_queryset().select_related("service", "service__plan"),
            pk=pk,
        )
        if not request.user.is_superuser and deploy.service.user_id != request.user.id:
            return Response(
                {"result": "error", "detail": _("Only owner can start deploy.")},
                status=status.HTTP_403_FORBIDDEN,
            )

        task_id = str(uuid4())
        platform = _resolve_platform(deploy)
        is_db = platform in DB_PLATFORMS
        _ensure_config_platform(deploy, platform)

        with transaction.atomic():
            service = Service.objects.select_for_update().get(pk=deploy.service_id)
            if service.status in (
                SERVICE_STATUS_CHOICES.QUEUED,
                SERVICE_STATUS_CHOICES.DEPLOYING,
                SERVICE_STATUS_CHOICES.STOPPING,
            ):
                return Response(
                    {"result": "error", "detail": _("This service already has an active operation.")},
                    status=status.HTTP_409_CONFLICT,
                )

            service.selected_deploy = deploy
            service.status = SERVICE_STATUS_CHOICES.QUEUED
            service.deploy_started = timezone.now()
            service.task_id = task_id
            service.save()

            Deploy.objects.filter(pk=deploy.pk).update(
                status="pending",
                stage="queued",
                progress=0,
                status_message="Deployment queued.",
                error_message="",
                cancel_requested=False,
            )

            deploy_pk = str(deploy.pk)
            if is_db:
                transaction.on_commit(
                    lambda: run_db_deploy.apply_async(args=[deploy_pk], task_id=task_id)
                )
            else:
                transaction.on_commit(
                    lambda: deploy_task.apply_async(args=[deploy_pk], task_id=task_id)
                )

        return Response({"result": "success", "task_id": task_id}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        deploy = get_object_or_404(self.get_queryset(), pk=pk)
        if not request.user.is_superuser and deploy.service.user_id != request.user.id:
            return Response(
                {"result": "error", "detail": _("Only owner can cancel deploy.")},
                status=status.HTTP_403_FORBIDDEN,
            )

        deploy.cancel_requested = True
        if deploy.status == "pending":
            deploy.status = "cancelled"
            deploy.stage = "cancelled"
            deploy.status_message = "Deployment cancelled before execution."
            deploy.completed_at = timezone.now()
            deploy.save(update_fields=["cancel_requested", "status", "stage", "status_message", "completed_at"])
        else:
            deploy.save(update_fields=["cancel_requested"])

        return Response(
            {"result": "success", "detail": _(f"Cancel requested for {deploy.name}.")},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def redeploy(self, request, pk=None):
        return self.start(request, pk)

    @action(detail=True, methods=["get"])
    def logs(self, request, pk=None):
        return deploy_logs_apiview(request, pk)

    @action(detail=True, methods=["post"])
    def rollback(self, request, pk=None):
        deploy = get_object_or_404(self.get_queryset(), pk=pk)
        if not request.user.is_superuser and deploy.service.user_id != request.user.id:
            return Response(
                {"result": "error", "detail": _("Only owner can rollback deploy.")},
                status=status.HTTP_403_FORBIDDEN,
            )

        deploy.rollback_status = "pending"
        deploy.save(update_fields=["rollback_status"])
        return Response(
            {"result": "success", "detail": _(f"Rollback requested for {deploy.name}.")},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def rebuild(self, request, pk=None):
        """
        Force rebuild: tear down the existing container (and image for app
        platforms), then queue a fresh deploy.

        DB platforms: remove container only (volumes preserved), then run_db_deploy.
        App platforms: remove container + image, then full rebuild from zip.
        """
        deploy = get_object_or_404(
            self.get_queryset().select_related("service", "service__plan"),
            pk=pk,
        )
        if not request.user.is_superuser and deploy.service.user_id != request.user.id:
            return Response(
                {"result": "error", "detail": _("Only owner can rebuild.")},
                status=status.HTTP_403_FORBIDDEN,
            )

        task_id = str(uuid4())
        platform = _resolve_platform(deploy)
        is_db = platform in DB_PLATFORMS
        _ensure_config_platform(deploy, platform)

        with transaction.atomic():
            service = Service.objects.select_for_update().get(pk=deploy.service_id)
            if service.status in (
                SERVICE_STATUS_CHOICES.QUEUED,
                SERVICE_STATUS_CHOICES.DEPLOYING,
                SERVICE_STATUS_CHOICES.STOPPING,
            ):
                return Response(
                    {"result": "error", "detail": _("Service already has an active operation.")},
                    status=status.HTTP_409_CONFLICT,
                )

            container_name = service.get_docker_service_name()
            try:
                if is_db:
                    DBDeployer().remove(container_name)
                else:
                    OrchestratorDeploy.remove_all(container_name)
            except Exception as exc:
                logger.warning(
                    "rebuild teardown warning for '%s': %s", container_name, exc
                )

            service.selected_deploy = deploy
            service.status = SERVICE_STATUS_CHOICES.QUEUED
            service.deploy_started = timezone.now()
            service.task_id = task_id
            service.save()

            Deploy.objects.filter(pk=deploy.pk).update(
                status="pending",
                stage="queued",
                progress=0,
                status_message="Rebuild queued.",
                error_message="",
                cancel_requested=False,
            )

            deploy_pk = str(deploy.pk)
            if is_db:
                transaction.on_commit(
                    lambda: run_db_deploy.apply_async(args=[deploy_pk], task_id=task_id)
                )
            else:
                transaction.on_commit(
                    lambda: deploy_task.apply_async(args=[deploy_pk], task_id=task_id)
                )

        return Response(
            {"result": "success", "task_id": task_id, "detail": _("Rebuild queued.")},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["patch"])
    def update_db_config(self, request, pk=None):
        """
        Safely update DB credentials in Deploy.config.
        Allowed keys: root_password, password, username, database, port, env.
        Does NOT restart — call /rebuild/ to apply.
        """
        deploy = get_object_or_404(
            self.get_queryset().select_related("service", "service__plan"),
            pk=pk,
        )
        if not request.user.is_superuser and deploy.service.user_id != request.user.id:
            return Response(
                {"result": "error", "detail": _("Only owner can update DB config.")},
                status=status.HTTP_403_FORBIDDEN,
            )

        cfg = dict(deploy.config) if isinstance(deploy.config, dict) else {}
        platform = _resolve_platform(deploy)
        if platform not in DB_PLATFORMS:
            return Response(
                {"result": "error", "detail": _("This deploy is not a DB platform.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updates = {k: v for k, v in request.data.items() if k in MUTABLE_DB_CONFIG_KEYS}
        if not updates:
            return Response(
                {
                    "result": "error",
                    "detail": _(
                        "No valid fields provided. "
                        f"Allowed: {', '.join(sorted(MUTABLE_DB_CONFIG_KEYS))}."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_cfg = {**cfg, **updates, "platform": platform}
        errors = validate_db_config(platform, new_cfg)
        if errors:
            return Response(
                {"result": "error", "detail": "; ".join(errors)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deploy.config = new_cfg
        deploy.save(update_fields=["config"])
        return Response(
            {
                "result": "success",
                "detail": _("DB config updated. Call /rebuild/ to apply the new credentials."),
            },
            status=status.HTTP_200_OK,
        )

    def update(self, request, pk=None, *args, **kwargs):
        deploy = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(deploy, data=request.data, partial=True)
        if serializer.is_valid():
            deploy = serializer.save()
            return Response(
                {"success": _("Deploy updated."), "deploy": self.get_serializer(deploy).data},
                status=status.HTTP_200_OK,
            )
        return Response(
            {"error": _("Can not update deploy."), "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def destroy(self, request, pk=None, *args, **kwargs):
        deploy = get_object_or_404(self.get_queryset(), pk=pk)
        deploy.delete()
        return Response({"success": _("Deploy deleted.")}, status=status.HTTP_200_OK)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def deploy_name_is_available(request):
    name = (request.query_params.get("name") or "").strip()
    exclude_id = (
        request.query_params.get("exclude_id")
        or request.query_params.get("exclude")
        or ""
    ).strip() or None

    if len(name) < 4:
        return Response(
            {"result": False, "detail": _("The length should be at least 4.")},
            status=status.HTTP_200_OK,
        )

    qs = Deploy.objects.filter(name=name)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)

    if qs.exists():
        return Response(
            {"result": False, "detail": _("The name has been taken.")},
            status=status.HTTP_200_OK,
        )
    return Response(
        {"result": True, "detail": _("The name is free.")},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def deploy_logs_apiview(request, pk):
    deploy = get_object_or_404(
        Deploy.objects.select_related("service", "service__user"),
        pk=pk,
    )
    if not request.user.is_superuser and deploy.service.user_id != request.user.id:
        return Response(
            {"result": "error", "detail": _("Only owner can view deployment logs.")},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        limit = min(max(int(request.query_params.get("limit", 10)), 1), 200)
    except ValueError:
        limit = 10

    before = request.query_params.get("before")
    after = request.query_params.get("after")

    base_qs = DeployLog.objects.using(settings.DEPLOYMENT_LOG_DB_ALIAS).filter(deploy_id=deploy.pk)

    if after:
        after_dt = _parse_cursor(after)
        if after_dt is None:
            return Response(
                {"result": "error", "detail": _("Invalid after timestamp.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rows = list(base_qs.filter(created_at__gt=after_dt).order_by("created_at")[:limit])
        next_after = rows[-1].created_at.isoformat() if rows else after
        return Response(
            {
                "result": "success",
                "deploy": DeploySerializer(deploy).data,
                "logs": DeployLogSerializer(rows, many=True).data,
                "next_after": next_after,
                "has_more_newer": len(rows) == limit,
                "direction": "forward",
            },
            status=status.HTTP_200_OK,
        )

    if before:
        before_dt = _parse_cursor(before)
        if before_dt is None:
            return Response(
                {"result": "error", "detail": _("Invalid before timestamp.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        queryset = base_qs.filter(created_at__lt=before_dt)
    else:
        queryset = base_qs

    rows_desc = list(queryset.order_by("-created_at")[: limit + 1])
    has_more_older = len(rows_desc) > limit
    rows_desc = rows_desc[:limit]
    rows = list(reversed(rows_desc))

    next_before = rows[0].created_at.isoformat() if rows else before
    latest_after = rows[-1].created_at.isoformat() if rows else before

    return Response(
        {
            "result": "success",
            "deploy": DeploySerializer(deploy).data,
            "logs": DeployLogSerializer(rows, many=True).data,
            "next_before": next_before,
            "latest_after": latest_after,
            "has_more_older": has_more_older,
            "direction": "backward",
        },
        status=status.HTTP_200_OK,
    )


def _extract_id(value):
    """Accept raw UUID string, int, or a dict/object with an 'id' field."""
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("id") or value.get("pk")
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("{") and "'id'" in value:
            import ast
            try:
                parsed = ast.literal_eval(value)
                if isinstance(parsed, dict):
                    value = parsed.get("id") or parsed.get("pk")
            except (ValueError, SyntaxError):
                pass
        return value or None
    return value


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def set_deploy_apiview(request):
    deploy_id = _extract_id(request.data.get("deploy_id"))
    service_id = _extract_id(request.data.get("service_id"))

    if not deploy_id or not service_id:
        return Response(
            {"result": "error", "detail": _("deploy_id and service_id are required.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        with transaction.atomic():
            service_item = Service.objects.select_for_update().get(
                id=service_id,
                user=request.user,
            )

            if service_item.status in (
                SERVICE_STATUS_CHOICES.QUEUED,
                SERVICE_STATUS_CHOICES.DEPLOYING,
                SERVICE_STATUS_CHOICES.STOPPING,
            ):
                return Response(
                    {
                        "result": "error",
                        "detail": _("You can't select deploy in (queued, deploying, stopping) modes."),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            deploy_item = Deploy.objects.select_related("service").get(id=deploy_id)

            if deploy_item.service_id != service_item.id:
                return Response(
                    {
                        "result": "error",
                        "detail": _("Deploy does not belong to this service."),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if deploy_item.service.user_id != request.user.id:
                return Response(
                    {
                        "result": "error",
                        "detail": _("Only owner can select deploy."),
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            service_item.selected_deploy = deploy_item
            service_item.save(update_fields=["selected_deploy"])

    except Service.DoesNotExist:
        return Response(
            {"result": "error", "detail": _("Service not found.")},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Deploy.DoesNotExist:
        return Response(
            {"result": "error", "detail": _("Deploy not found.")},
            status=status.HTTP_404_NOT_FOUND,
        )
    except (ValueError, ValidationError):
        return Response(
            {"result": "error", "detail": _("Invalid deploy_id or service_id.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "result": "success",
            "detail": _(f"Deploy {deploy_item.name} selected."),
            "selected_deploy": str(deploy_item.id),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def unset_deploy_apiview(request):
    deploy_id = _extract_id(request.data.get("deploy_id"))
    service_id = _extract_id(request.data.get("service_id"))

    if not deploy_id or not service_id:
        return Response(
            {"result": "error", "detail": _("deploy_id and service_id are required.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        with transaction.atomic():
            service_item = Service.objects.select_for_update().get(
                id=service_id,
                user=request.user,
            )

            if service_item.status in (
                SERVICE_STATUS_CHOICES.QUEUED,
                SERVICE_STATUS_CHOICES.DEPLOYING,
                SERVICE_STATUS_CHOICES.STOPPING,
            ):
                return Response(
                    {
                        "result": "error",
                        "detail": _("You can't unselect deploy in (queued, deploying, stopping) modes."),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            deploy_item = Deploy.objects.select_related("service").get(id=deploy_id)

            if deploy_item.service.user_id != request.user.id:
                return Response(
                    {
                        "result": "error",
                        "detail": _("Only owner can unselect deploy."),
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            if service_item.selected_deploy_id != deploy_item.id:
                return Response(
                    {
                        "result": "error",
                        "detail": _("This deploy is not selected for the service."),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            service_item.selected_deploy = None
            service_item.save(update_fields=["selected_deploy"])

    except Service.DoesNotExist:
        return Response(
            {"result": "error", "detail": _("Service not found.")},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Deploy.DoesNotExist:
        return Response(
            {"result": "error", "detail": _("Deploy not found.")},
            status=status.HTTP_404_NOT_FOUND,
        )
    except (ValueError, ValidationError):
        return Response(
            {"result": "error", "detail": _("Invalid deploy_id or service_id.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "result": "success",
            "detail": _(f"Deploy {deploy_item.name} unselected."),
        },
        status=status.HTTP_200_OK,
    )
