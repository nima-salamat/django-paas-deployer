import functools
import os
import tarfile
import tempfile
from django.core.serializers import serialize
from django.db import transaction
from django.http import FileResponse
from .models import Service, PrivateNetwork, Volume
from deploy.models import Deploy
from django.shortcuts import get_object_or_404
from .serializers import PrivateNetworkSerializer, ServiceSerializer, VolumeSerializer, GetServiceSerializer
from rest_framework.viewsets import ViewSet, ModelViewSet
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from deployments.celery.tasks import deploy as start_service
from deployments.celery.tasks import stop as stop_service
from core.global_settings.config import SERVICE_STATUS_CHOICES
from core.utils import make_uuid4
from deployments.core.manager.container_manager import Container
from deployments.core.manager.client_manager import Client
from docker.errors import APIError, NotFound as DockerNotFound



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
        # if self.request.user.is_superuser:
            # return queryset
        return queryset.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        query = self.get_queryset()
        # ?q_search = ddfdf
        print(request.query_params)
        q_search_param =  request.query_params.get("q_search")
        if q_search_param:
            query = query.filter(name__contains=q_search_param)

        page = self.paginate_queryset(query)
        serializer = GetServiceSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        # if not request.user.is_superuser:
        request.data["user"] = request.user.id

        network_id = request.data.get("network", None)
        if not network_id or not PrivateNetwork.objects.filter(id=network_id,user=request.user).exists():
            return Response({"error": _("You must create a Private Network first.")}, status=status.HTTP_400_BAD_REQUEST)
            
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"success": _("Service created.")}, status=status.HTTP_201_CREATED)
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None, *args, **kwargs):
        service = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(service, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"success": _("Service updated.")}, status=status.HTTP_200_OK)
        return Response({"error": _("Can not update service."),"errors":serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None, *args, **kwargs):
        service = get_object_or_404(self.get_queryset(), pk=pk)
        if service.status in (
            SERVICE_STATUS_CHOICES.QUEUED,
            SERVICE_STATUS_CHOICES.DEPLOYING,
            SERVICE_STATUS_CHOICES.STOPPING
        ):
            return Response({"result":"error", "detail":_(f"Service is in '{service.status}' mode.")}, status=status.HTTP_409_CONFLICT)
        
        service.delete()
        return Response({"success": _("Service deleted.")}, status=status.HTTP_200_OK)


class PrivateNetworkViewSet(ModelViewSet):
    queryset = PrivateNetwork.objects.all()
    serializer_class = PrivateNetworkSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = ServiceAdminPagination

    def get_queryset(self):
        # if self.request.user.is_superuser:
            # return super().get_queryset()
        return super().get_queryset().filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        # if not request.user.is_superuser:
        request.data["user"] = request.user.id
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response({"success": _("Private Network created.")}, status=status.HTTP_201_CREATED)
        return Response({"error": _("Can not create network."), "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None, *args, **kwargs):
        network = get_object_or_404(self.get_queryset(), pk=pk, user=request.user)
        serializer = self.get_serializer(network, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"success": _("Private Network updated.")}, status=status.HTTP_200_OK)
        return Response({"error": _("Can not update network"), "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    def destroy(self, request, pk=None, *args, **kwargs):
        network = get_object_or_404(self.get_queryset(), pk=pk, user=request.user)
        
        if Service.objects.filter(network=network).exists():
            return Response(
                {"result": "error", "detail": _("Cannot delete network with active services.")},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        network.delete()
        return Response(
            {"success": _("Private Network deleted.")},
            status=status.HTTP_200_OK
        )


class VolumeViewSet(ModelViewSet):
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
        queryset = self.get_queryset()
        service_id = request.query_params.get("service")
        unused = request.query_params.get("unused")
        if service_id:
            queryset = queryset.filter(service_id=service_id)
        if unused is not None and str(unused).lower() in ("1", "true", "yes"):
            queryset = queryset.filter(service__isnull=True)
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            service_obj = serializer.validated_data.get("service")
            if service_obj and service_obj.user != request.user:
                return Response({"error": _("Selected service does not belong to the authenticated user.")}, status=status.HTTP_400_BAD_REQUEST)
            serializer.save(user=request.user)
            return Response({"success": _("Volume created.")}, status=status.HTTP_201_CREATED)
        return Response({"error": _("Can not create Volume."), "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None, *args, **kwargs):
        volume = get_object_or_404(self.get_queryset(), pk=pk, user=request.user)
        serializer = self.get_serializer(volume, data=request.data, partial=True)
        if serializer.is_valid():
            service_obj = serializer.validated_data.get("service")
            if service_obj and service_obj.user != request.user:
                return Response({"error": _("Selected service does not belong to the authenticated user.")}, status=status.HTTP_400_BAD_REQUEST)
            serializer.save()
            return Response({"success": _("Volume updated.")}, status=status.HTTP_200_OK)
        return Response({"error": _("Can not update Volume"), "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None, *args, **kwargs):
        volume = get_object_or_404(self.get_queryset(), pk=pk, user=request.user)
        if volume.service and volume.service.status in (
            SERVICE_STATUS_CHOICES.QUEUED,
            SERVICE_STATUS_CHOICES.DEPLOYING,
            SERVICE_STATUS_CHOICES.RUNNING,
            SERVICE_STATUS_CHOICES.STOPPING,
        ):
            return Response({"error": _("Cannot delete a volume attached to an active service.")}, status=status.HTTP_409_CONFLICT)
        volume.delete()
        return Response({"success": _("Volume deleted.")}, status=status.HTTP_200_OK)


def _get_volume_mountpoint(name: str):
    client = Client()()
    volume = client.volumes.get(name)
    mountpoint = volume.attrs.get("Mountpoint")
    if not mountpoint or not os.path.isdir(mountpoint):
        raise ValueError("Volume mountpoint is unavailable.")
    return mountpoint


def _list_volume_files(root_path):
    files = []
    for base, dirs, filenames in os.walk(root_path):
        rel_base = os.path.relpath(base, root_path)
        if rel_base == ".":
            rel_base = ""
        for dirname in dirs:
            path = os.path.join(rel_base, dirname)
            full = os.path.join(base, dirname)
            stats = os.stat(full)
            files.append({
                "path": path,
                "type": "directory",
                "size": 0,
                "modified_at": stats.st_mtime,
            })
        for filename in filenames:
            path = os.path.join(rel_base, filename)
            full = os.path.join(base, filename)
            stats = os.stat(full)
            files.append({
                "path": path,
                "type": "file",
                "size": stats.st_size,
                "modified_at": stats.st_mtime,
            })
    return files


def _create_volume_archive(root_path, archive_name):
    temp_file = tempfile.NamedTemporaryFile(prefix="volume_archive_", suffix=".tar.gz", delete=False)
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
        mountpoint = _get_volume_mountpoint(volume.name)
        files = _list_volume_files(mountpoint)
        return Response({"result": "success", "files": files}, status=status.HTTP_200_OK)
    except DockerNotFound:
        return Response({"result": "error", "detail": _("Docker volume not found.")}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"result": "error", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        return Response({"result": "error", "detail": _("Unable to list volume files.")}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def volume_download_apiview(request, pk):
    volume = get_object_or_404(Volume.objects.filter(user=request.user), pk=pk)
    try:
        mountpoint = _get_volume_mountpoint(volume.name)
        archive_path = _create_volume_archive(mountpoint, volume.name)
        response = FileResponse(open(archive_path, "rb"), as_attachment=True, filename=f"{volume.name}.tar.gz")
        response['Content-Length'] = os.path.getsize(archive_path)
        response['Content-Type'] = 'application/gzip'
        return response
    except DockerNotFound:
        return Response({"result": "error", "detail": _("Docker volume not found.")}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"result": "error", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        return Response({"result": "error", "detail": _("Unable to create volume archive.")}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
        return Response({"result": "success", "logs": decoded.splitlines()}, status=status.HTTP_200_OK)
    except DockerNotFound:
        return Response({"result": "error", "detail": _("Service container not found.")}, status=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return Response({"result": "error", "detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def start_service_apiview(request):
    service_id = request.data.get("service_id", "")
    
    try:    
        with transaction.atomic():
            service_item = Service.objects.select_for_update().get(
                id=service_id, 
                user=request.user
            )
            deploy_item = service_item.selected_deploy
            if deploy_item is None:
                return Response(
                    {
                        "result": "error",
                        "detail": _("First select a deploy.")
                    },
                    status=status.HTTP_409_CONFLICT
                )
            
            if service_item.status in (
                SERVICE_STATUS_CHOICES.QUEUED, 
                SERVICE_STATUS_CHOICES.DEPLOYING,
                SERVICE_STATUS_CHOICES.STOPPING
            ):
                return Response(
                    {
                        "result": "error",
                        "detail": _("You can't start service in (queued, deploying, stopping) modes.")
                    },
                    status=status.HTTP_409_CONFLICT
                )
            
            service_item.status = SERVICE_STATUS_CHOICES.QUEUED
            service_item.deploy_started = timezone.now()
            service_item.task_id = make_uuid4()
            service_item.save()
            Deploy.objects.filter(pk=deploy_item.pk).update(
                status="pending",
                stage="queued",
                progress=0,
                status_message="Deployment queued.",
                error_message="",
                cancel_requested=False,
            )
            transaction.on_commit(
                functools.partial(start_service.apply_async, args=[str(deploy_item.id)], task_id=service_item.task_id)
            )
            
    except Service.DoesNotExist:
        return Response(
            {
                "result": "error",
                "detail": _(f"Service with this ID:{service_id} not found.")
            },
            status=status.HTTP_404_NOT_FOUND
        )
    
    return Response(
        {
            "result": "success",
            "detail": _("Service started.")
        }, 
        status=status.HTTP_202_ACCEPTED
    )

@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def stop_service_apiview(request):
    service_id = request.data.get("service_id", "")
    
    try:    
        with transaction.atomic():
            service_item = Service.objects.select_for_update().get(
                id=service_id,
                user=request.user
            )
            
            if service_item.status in (
                SERVICE_STATUS_CHOICES.QUEUED, 
                SERVICE_STATUS_CHOICES.DEPLOYING,
                SERVICE_STATUS_CHOICES.STOPPING
            ):
                return Response({
                    "result": "error",
                    "detail": _("You can't stop service in (queued, deploying, stopping) modes.")
                    },
                    status=status.HTTP_409_CONFLICT 
                )
            
            custom_task_id = make_uuid4()
            
            service_item.status = SERVICE_STATUS_CHOICES.QUEUED
            service_item.task_id = custom_task_id
            service_item.save()

            transaction.on_commit(
                lambda: stop_service.apply_async(
                    args=[str(service_id)],
                    task_id = custom_task_id
                )
            )
            
            
    except Service.DoesNotExist:
        return Response(
            {
                "result": "error", 
                "detail": _(f"Service with this ID:{service_id} not found.")
            },
            status=status.HTTP_404_NOT_FOUND
        )
    
    return Response(
        {
            "result": "success", 
            "detail": _("Service stopped.")
        }, 
        status=status.HTTP_202_ACCEPTED
    )
    

@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def service_status_apiview(request):
    service_id = request.data.get("service_id", "")

    try:
        service_item = Service.objects.get(
            id=service_id,
            user=request.user
        )
    except Service.DoesNotExist:
        return Response(
            {
                "result": "error",
                "running": False,
                "cpu": 0,
                "ram": 0,
                "detail": _("Service with the ID not found.")
            },
            status=status.HTTP_404_NOT_FOUND
        )

    name = service_item.get_docker_service_name()
    print(name)
    try:
        container = Container(name=name)
        stats = container.get_container_stats()
        print(stats)
        running = stats.get("running", 0) == 1
        cpu = stats.get("cpu", 0.0)
        ram = stats.get("memory", 0.0)
        detail = _("Service is running.") if running else _("Service is not running.")
    except Exception as e:
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
            "detail": detail
        },
        status=status.HTTP_200_OK
    )
