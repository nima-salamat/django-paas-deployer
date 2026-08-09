# deploy/apis.py
import functools
import json
import logging
import os
import secrets
import shutil
import string
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
from deployments.celery.tasks import run_db_deploy  # DB platforms — NOT deploy.tasks
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
from services.models import Service
from core.utils import make_uuid4

logger = logging.getLogger(__name__)


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
    """
    Resolve platform for routing DB vs app deploy tasks.

    Order: deploy.config["platform"] → service.plan.platform → "docker".
    """
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
            logger.exception("Failed to resolve plan.platform for deploy %s", getattr(deploy, "pk", None))

    return "docker"


def _ensure_config_platform(deploy, platform: str) -> dict:
    """Persist platform onto deploy.config when missing so later starts stay correct."""
    cfg = _parse_deploy_config(getattr(deploy, "config", None))
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

        data = dict(request.data.items())
        
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
                
      
        if not cfg:
            for key, value in request.data.items():
                key_str = str(key)
                if key_str.startswith("config[") and key_str.endswith("]"):
                    sub_key = key_str[7:-1]
                    cfg[sub_key] = value

        if not cfg.get("platform") and service_id:
            try:
                service = Service.objects.select_related("plan").get(pk=service_id)
                if service.plan and getattr(service.plan, "platform", None):
                    cfg["platform"] = str(service.plan.platform).strip().lower()
            except Service.DoesNotExist:
                pass

        data["config"] = cfg

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

        cfg = _parse_deploy_config(getattr(deploy, "config", None))
        platform = _resolve_platform(deploy)
        if platform not in DB_PLATFORMS:
            return Response(
                {"result": "error", "detail": _("This deploy is not a DB platform.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Skip empty/null sentinels for password-type keys so a user
        # editing the deploy via the form (which can't pre-fill passwords
        # because they're masked in the API response) can leave password
        # fields empty without overwriting the existing password with "".
        # For non-password fields (env, port, etc.), an empty value is a
        # legitimate "clear this" intent, so we still pass it through.
        PASSWORD_KEYS = {"password", "root_password"}
        updates = {}
        for k, v in request.data.items():
            if k not in MUTABLE_DB_CONFIG_KEYS:
                continue
            if k in PASSWORD_KEYS and v in (None, "", "__unchanged__"):
                # Keep existing password — don't overwrite.
                continue
            updates[k] = v
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

        # For DB-platform deploys, the generic update would normally
        # overwrite the entire ``config`` JSONField with whatever the
        # client sends.  That's dangerous because the form cannot
        # pre-fill password fields (they're masked in the API response),
        # so a user editing just the username would accidentally wipe
        # the password to "".
        #
        # Defense in depth: if this is a DB platform and the request
        # includes a ``config`` dict, merge it with the existing config
        # and drop any empty password sentinels before saving.
        data = request.data
        if hasattr(data, "_mutable"):
            try:
                data._mutable = True
            except Exception:
                pass
        data = dict(data) if hasattr(data, "items") else dict(data)

        platform = _resolve_platform(deploy)
        if platform in DB_PLATFORMS and isinstance(data.get("config"), dict):
            existing_cfg = _parse_deploy_config(getattr(deploy, "config", None))
            incoming = dict(data["config"])
            # Drop empty password sentinels — keep existing password.
            for pw_key in ("password", "root_password"):
                if incoming.get(pw_key) in (None, "", "__unchanged__"):
                    incoming.pop(pw_key, None)
            # Merge: existing values are the base; incoming values win
            # for any key the client explicitly sent (except dropped
            # password sentinels).  Always preserve platform.
            merged = {**existing_cfg, **incoming, "platform": platform}
            data["config"] = merged
        elif platform in DB_PLATFORMS and isinstance(data.get("config"), str):
            # Client sent config as a JSON string (e.g. from a textarea).
            # Parse it, drop password sentinels, re-merge, re-stringify.
            try:
                incoming = json.loads(data["config"]) if data["config"].strip() else {}
                if not isinstance(incoming, dict):
                    incoming = {}
            except (json.JSONDecodeError, ValueError):
                # Let the serializer surface the validation error.
                incoming = None
            if incoming is not None:
                existing_cfg = _parse_deploy_config(getattr(deploy, "config", None))
                for pw_key in ("password", "root_password"):
                    if incoming.get(pw_key) in (None, "", "__unchanged__"):
                        incoming.pop(pw_key, None)
                merged = {**existing_cfg, **incoming, "platform": platform}
                data["config"] = json.dumps(merged)

        serializer = self.get_serializer(deploy, data=data, partial=True)
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

    @action(detail=True, methods=["get"])
    def reveal_db_credentials(self, request, pk=None):
        """
        Return the FULL DB config including sensitive fields (password,
        root_password, username) that are masked by DeploySerializer.

        The default ``retrieve`` endpoint strips these via
        ``MaskedDBConfigField`` so they don't leak into every list/retrieve
        response.  This endpoint exists specifically for the service-detail
        UI's "Database" overview card, which needs the credentials to:
          1. Show them in the overview (so the user can copy them).
          2. Pre-fill the edit form (so the user doesn't lose the
             password by saving with an empty field).

        Security:
          * Owner-only (403 for non-owners, even superusers see only
            their own unless they're superusers).
          * Returns 400 for non-DB deploys.
          * Logs the reveal event for audit (INFO level).
        """
        deploy = get_object_or_404(
            self.get_queryset().select_related("service", "service__plan"),
            pk=pk,
        )
        if not request.user.is_superuser and deploy.service.user_id != request.user.id:
            return Response(
                {"result": "error", "detail": _("Only owner can reveal DB credentials.")},
                status=status.HTTP_403_FORBIDDEN,
            )

        platform = _resolve_platform(deploy)
        if platform not in DB_PLATFORMS:
            return Response(
                {"result": "error", "detail": _("This deploy is not a DB platform.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cfg = _parse_deploy_config(getattr(deploy, "config", None))
        # Audit log — record that someone revealed the credentials.
        logger.info(
            "DB credentials revealed for deploy %s (platform=%s, user=%s).",
            deploy.pk, platform, request.user.pk,
        )
        return Response(
            {
                "result": "success",
                "platform": platform,
                "config": cfg,
            },
            status=status.HTTP_200_OK,
        )


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


# ---------------------------------------------------------------------------
# Credential generation
# ---------------------------------------------------------------------------

# Safe alphabet for DB passwords — excludes characters that break:
#   * URL encoding in connection strings (`@`, `:`, `/`, `#`, `?`)
#   * Shell quoting (`'`, `"`, `` ` ``, `\`, `$`)
#   * SQL string literals (`'`, `"`)
#   * JSON string escaping (`"`, `\`)
#   * Whitespace (space, tab, newline — break copy-paste and config files)
# Includes a healthy mix of upper/lower/digits/symbols so the password
# satisfies typical DB password policy requirements.
_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#%^&*()-_=+"
_DB_USERNAME_ALPHABET = string.ascii_lowercase + string.digits


def _generate_password(length: int = 24) -> str:
    """Generate a cryptographically-secure random DB password."""
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def _generate_db_username(platform: str) -> str:
    """Generate a DB-safe username like 'mysql_user_a3f9k2'."""
    suffix = "".join(secrets.choice(_DB_USERNAME_ALPHABET) for _ in range(6))
    return f"{platform}_user_{suffix}"


def _generate_db_name(platform: str) -> str:
    """Generate a DB-safe database name like 'mysql_db_7hq2x9p4'."""
    suffix = "".join(secrets.choice(_DB_USERNAME_ALPHABET) for _ in range(8))
    return f"{platform}_db_{suffix}"


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def generate_db_credentials_apiview(request):
    """
    POST /deploy/generate_db_credentials/  body: {"platform": "mysql"}
    Returns: {"username", "password", "root_password", "database", "port"}

    Generates a random, DB-safe set of credentials that the frontend can
    auto-fill into the Create Deploy form.  This endpoint exists for
    parity with the frontend's client-side generator (so the same
    generator can be reused server-side if needed, e.g. for API-only
    clients).  The frontend uses its own client-side generator by
    default — no network round-trip, secrets never leave the browser.

    The generated values follow these rules:
      * username: ``<platform>_user_<6 random lowercase+digits>`` (≤32 chars)
      * password: 24 chars from a safe alphabet (no quotes, backticks,
        dollar signs, semicolons, spaces, or URL-reserved chars)
      * root_password: same as password (only for mysql/mariadb)
      * database: ``<platform>_db_<8 random lowercase+digits>`` (≤64 chars)
      * port: null (use platform default — backend picks the standard
        port per platform)
    """
    platform = (request.data.get("platform") or "").strip().lower()
    if not platform:
        return Response(
            {"result": "error", "detail": _("'platform' field is required.")},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if platform not in DB_PLATFORMS:
        return Response(
            {
                "result": "error",
                "detail": _(
                    f"Unsupported DB platform '{platform}'. "
                    f"Supported: {', '.join(sorted(DB_PLATFORMS))}."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    creds = {
        "username": _generate_db_username(platform),
        "password": _generate_password(24),
        "database": _generate_db_name(platform),
        "port": None,
    }
    # MySQL/MariaDB use root_password; other platforms don't.
    if platform in ("mysql", "mariadb"):
        creds["root_password"] = _generate_password(24)

    return Response(
        {"result": "success", "platform": platform, "credentials": creds},
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# ZIP inspection — suggest deploy config from uploaded project
# ---------------------------------------------------------------------------

@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def inspect_deploy_zip_apiview(request):
    """
    POST /deploy/inspect_zip/  (multipart: file=<zip>)
    Returns: {
        "platform": "django"|"node-express"|...,
        "framework": "django"|"express"|...,
        "server_type": "wsgi"|"asgi"|null,
        "entrypoint": "<start_command>"|null,
        "django_settings_module": "myproject.settings"|null,
        "static_dir": "/app/static"|null,
        "media_dir": "/app/media"|null,
        "suggested_config": { ... },  # ready-to-paste JSON for the config field
        "markers": ["manage.py", "requirements.txt", ...],  # detected marker files
        "raw": { ... },  # the full platform inspection result, for debugging
    }

    Reuses the existing ``extract_zip_to_temp`` + ``enrich_config_from_project``
    infrastructure from ``deployments.core.platform_bridge``.  The endpoint
    is read-only — it does NOT create a Deploy, just inspects the zip and
    returns a suggested config that the user can review and edit before
    submitting the actual create form.

    Security:
      * Reuses the same zip-safety checks as the deploy endpoint (Zip-Slip
        protection, size caps, symlink rejection) via ``extract_zip_to_temp``.
      * Temp files are cleaned up in a ``finally`` block.
      * No authentication beyond ``IsAuthenticated`` — any logged-in user
        can inspect any zip they upload.  The zip is never persisted.
    """
    uploaded = request.FILES.get("file")
    if not uploaded:
        return Response(
            {"result": "error", "detail": _("'file' field is required (multipart upload).")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Reject obviously non-zip uploads early — the extraction code would
    # catch this too, but a clean 400 is friendlier than a 500.
    if not (uploaded.name or "").lower().endswith(".zip"):
        return Response(
            {"result": "error", "detail": _("File must be a .zip archive.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Save to a temp file — extract_zip_to_temp takes a path, not a file.
    tmp_zip_path = None
    tmp_dir = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".zip", delete=False, prefix="deploy-inspect-"
        ) as tmp:
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            tmp_zip_path = tmp.name

        # Import here so the import-failure doesn't break the whole module
        # if the deployments package is in a weird state.
        try:
            from deployments.core.platform_bridge import (
                extract_zip_to_temp,
                enrich_config_from_project,
            )
            from deployments.core.types import DeploymentConfig
            from deployments.core.platforms.registry import PlatformRegistry
        except ImportError as exc:
            logger.exception("Failed to import platform inspection modules: %s", exc)
            return Response(
                {
                    "result": "error",
                    "detail": _(
                        "Platform inspection is not available on this server. "
                        "Please write the config JSON manually."
                    ),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            tmp_dir, project_root = extract_zip_to_temp(tmp_zip_path)
        except (ValueError, FileNotFoundError) as exc:
            return Response(
                {"result": "error", "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build a minimal DeploymentConfig to feed into enrich_config_from_project.
        # enrich_config_from_project only fills EMPTY fields, so we pass a
        # config with platform unset (let the detector pick) and all other
        # fields at their defaults / None.
        try:
            config = DeploymentConfig(
                name="inspect",
                tag="inspect",
                zip_path=tmp_zip_path,
                dockerfile_template="",
                max_cpu=1.0,
                max_ram=512,
                networks=[],
                volumes=[],
                port=None,
                read_only=False,
                platform="docker",  # placeholder — enrich will overwrite
                platform_type="app",
            )
        except TypeError:
            # DeploymentConfig signature changed — fall back to a plain dict.
            config = None

        detection_raw = {}
        suggested_config: dict = {}
        markers: list[str] = []
        if config is not None:
            try:
                enriched = enrich_config_from_project(config, project_root)
                # Pull the detection result back out for the response.
                suggested_config = {
                    "platform": enriched.platform or "docker",
                }
                if enriched.server_type:
                    suggested_config["server_type"] = enriched.server_type
                if enriched.entry_point:
                    suggested_config["entry_point"] = enriched.entry_point
                suggested_config["celery"] = bool(enriched.celery)
                suggested_config["celery_beat"] = bool(enriched.celery_beat)
                suggested_config["worker_count"] = int(enriched.worker_count or 1)

                # Try to get the raw detection result for extra fields
                # (django_settings_module, static_dir, etc.) that aren't
                # on DeploymentConfig itself.
                try:
                    from deployments.core.platform_bridge import get_project_cfg
                    project_cfg = get_project_cfg(enriched)
                    if project_cfg is not None:
                        detection_raw = {
                            k: v for k, v in vars(project_cfg).items()
                            if not k.startswith("_") and _json_safe(v)
                        }
                        # Markers are the files the detector found.
                        markers = list(getattr(project_cfg, "markers", []) or [])
                except Exception:
                    pass
            except Exception as exc:
                logger.warning(
                    "enrich_config_from_project failed during zip inspection: %s",
                    exc, exc_info=True,
                )

        # If we have markers from the inspector directly, use those.
        if not markers:
            try:
                from deployments.core.platforms.inspector import ProjectInspector
                inspector = ProjectInspector(project_root)
                # ProjectInspector populates self.markers during __init__
                # (or via a scan() method) — try both shapes for safety.
                if hasattr(inspector, "markers") and isinstance(inspector.markers, list):
                    markers = sorted(inspector.markers)
                elif hasattr(inspector, "scan"):
                    inspector.scan()
                    markers = sorted(getattr(inspector, "markers", []) or [])
            except Exception:
                # Marker detection is best-effort — don't fail the request.
                markers = []

        return Response(
            {
                "result": "success",
                "platform": suggested_config.get("platform"),
                "framework": detection_raw.get("framework"),
                "server_type": suggested_config.get("server_type"),
                "entrypoint": suggested_config.get("entry_point"),
                "django_settings_module": detection_raw.get("django_settings_module"),
                "static_dir": detection_raw.get("static_dir"),
                "media_dir": detection_raw.get("media_dir"),
                "suggested_config": suggested_config,
                "markers": markers,
                "raw": detection_raw,
            },
            status=status.HTTP_200_OK,
        )

    finally:
        # Cleanup — never leave temp files behind.
        if tmp_dir and os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
        if tmp_zip_path and os.path.exists(tmp_zip_path):
            try:
                os.unlink(tmp_zip_path)
            except OSError:
                pass


def _json_safe(value) -> bool:
    """Return True if ``value`` is JSON-serializable (for the inspect endpoint)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_json_safe(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _json_safe(v) for k, v in value.items())
    return False
