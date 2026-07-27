from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response
from rest_framework.decorators import api_view, authentication_classes, permission_classes, action
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.db import transaction
from django.utils import timezone
from uuid import uuid4
from .models import Deploy, DeployLog
from services.models import Service
from .serializers import DeployLogSerializer, DeploySerializer

from core.global_settings.config import SERVICE_STATUS_CHOICES
from deployments.celery.tasks import deploy as deploy_task


class DeployPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class DeployViewSet(ModelViewSet):
    queryset = Deploy.objects.all()
    serializer_class = DeploySerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = DeployPagination

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.select_related("service", "service__user").prefetch_related("logs")
        if self.request.user.is_superuser:
            return qs
        return qs.filter(service__user=self.request.user)

    def list(self, request, *args, **kwargs):
        service_id = request.query_params.get("service_id","")
        queryset = self.get_queryset().order_by("created_at")
        if service_id:
            queryset = queryset.filter(service = service_id)
        page = self.paginate_queryset(queryset = queryset)
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
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            deploy = serializer.save()
            return Response(
                {"success": _("Deploy created."), "deploy": self.get_serializer(deploy).data},
                status=status.HTTP_201_CREATED,
            )
        return Response({"error": _("Can not deploy."), "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])  # POST /deploy/<pk>/start/
    def start(self, request, pk=None):
        deploy = get_object_or_404(self.get_queryset(), pk=pk)
        # permission check
        if not request.user.is_superuser and deploy.service.user_id != request.user.id:
            return Response({"result": "error", "detail": _("Only owner can start deploy.")}, status=status.HTTP_403_FORBIDDEN)

        task_id = str(uuid4())
        with transaction.atomic():
            service = Service.objects.select_for_update().get(pk=deploy.service_id)
            if service.status in (SERVICE_STATUS_CHOICES.QUEUED, SERVICE_STATUS_CHOICES.DEPLOYING, SERVICE_STATUS_CHOICES.STOPPING):
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
            transaction.on_commit(lambda: deploy_task.apply_async(args=[str(deploy.pk)], task_id=task_id))
        return Response({"result": "success", "task_id": task_id}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        deploy = get_object_or_404(self.get_queryset(), pk=pk)
        if not request.user.is_superuser and deploy.service.user_id != request.user.id:
            return Response({"result": "error", "detail": _("Only owner can cancel deploy.")}, status=status.HTTP_403_FORBIDDEN)
        deploy.cancel_requested = True
        if deploy.status == "pending":
            deploy.status = "cancelled"
            deploy.stage = "cancelled"
            deploy.status_message = "Deployment cancelled before execution."
            deploy.completed_at = timezone.now()
            deploy.save(update_fields=["cancel_requested", "status", "stage", "status_message", "completed_at"])
        else:
            deploy.save(update_fields=["cancel_requested"])
        return Response({"result": "success", "detail": _(f"Cancel requested for {deploy.name}.")}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def redeploy(self, request, pk=None):
        # simply call start again — clients can bump version in body if needed
        return self.start(request, pk)

    @action(detail=True, methods=["post"])
    def logs(self, request, pk=None):
        # proxy to existing deploy_logs_apiview
        return deploy_logs_apiview(request, pk)

    @action(detail=True, methods=["post"])
    def rollback(self, request, pk=None):
        deploy = get_object_or_404(self.get_queryset(), pk=pk)
        if not request.user.is_superuser and deploy.service.user_id != request.user.id:
            return Response({"result": "error", "detail": _("Only owner can rollback deploy.")}, status=status.HTTP_403_FORBIDDEN)
        # For now: mark rollback requested; orchestrator handles rollback on failure
        deploy.rollback_status = "pending"
        deploy.save(update_fields=["rollback_status"]) 
        return Response({"result": "success", "detail": _(f"Rollback requested for {deploy.name}.")}, status=status.HTTP_200_OK)

    def update(self, request, pk=None, *args, **kwargs):
        deploy = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(deploy, data=request.data, partial=True)
        if serializer.is_valid():
            deploy = serializer.save()
            return Response(
                {"success": _("Deploy updated."), "deploy": self.get_serializer(deploy).data},
                status=status.HTTP_200_OK,
            )
        return Response({"error": _("Can not update deploy."), "errors":serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None, *args, **kwargs):
        deploy = get_object_or_404(self.get_queryset(), pk=pk)
        deploy.delete()
        return Response({"success": _("Deploy deleted.")}, status=status.HTTP_200_OK)

@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def deploy_name_is_available(request):
    name = request.query_params.get("name", "")
    if len(name) < 4:
        return Response({"result": False, "detail": _("The length should be at least 4.")})
        
    if Deploy.objects.filter(name=name).exists():
        return Response({"result": False, "detail": _("The name has been taken.")})
    return Response({"result": True, "detail": _("The name is free.")})


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
        limit = min(max(int(request.query_params.get("limit", 100)), 1), 500)
    except ValueError:
        limit = 100

    after = request.query_params.get("after")
    queryset = DeployLog.objects.filter(deploy=deploy).order_by("created_at")
    if after:
        queryset = queryset.filter(created_at__gt=after)

    logs = list(queryset[:limit])
    return Response(
        {
            "result": "success",
            "deploy": DeploySerializer(deploy).data,
            "logs": DeployLogSerializer(logs, many=True).data,
        },
        status=status.HTTP_200_OK,
    )



@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def set_deploy_apiview(request):
    deploy_id = request.data.get("deploy_id")
    service_id = request.data.get("service_id")

    try:
        with transaction.atomic():
            service_item = Service.objects.select_for_update().get(
                id=service_id,
                user=request.user
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

            if deploy_item.service.user != request.user:
                return Response(
                    {
                        "result": "error",
                        "detail": _("Only owner can select deploy."),
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            service_item.selected_deploy = deploy_item
            service_item.save()

    except Service.DoesNotExist:
        return Response(
            {
                "result": "error",
                "detail": _("Service not found."),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    except Deploy.DoesNotExist:
        return Response(
            {
                "result": "error",
                "detail": _("Deploy not found."),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {
            "result": "success",
            "detail": _(f"Deploy {deploy_item.name} selected."),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def unset_deploy_apiview(request):
    deploy_id = request.data.get("deploy_id")
    service_id = request.data.get("service_id")

    try:
        with transaction.atomic():
            service_item = Service.objects.select_for_update().get(
                id=service_id,
                user=request.user
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

            if deploy_item.service.user != request.user:
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
            service_item.save()

    except Service.DoesNotExist:
        return Response(
            {
                "result": "error",
                "detail": _("Service not found."),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    except Deploy.DoesNotExist:
        return Response(
            {
                "result": "error",
                "detail": _("Deploy not found."),
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {
            "result": "success",
            "detail": _(f"Deploy {deploy_item.name} unselected."),
        },
        status=status.HTTP_200_OK,
    )
