import functools
from django.core.serializers import serialize
from django.db import transaction
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
from deployments.tasks.deploy import deploy as start_service
from deployments.tasks.deploy import stop as stop_service
from core.global_settings.config import SERVICE_STATUS_CHOICES
from deployments.core.manager.container_manager import Container



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
        service.delete()
        return Response({"success": ("Service deleted.")}, status=status.HTTP_200_OK)


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
        network.delete()
        return Response({"success": _("Private Network deleted.")}, status=status.HTTP_200_OK)

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
        page = self.paginate_queryset(self.get_queryset())
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid:
            serializer.save()
            return Response({"success": _("Volume created.")}, status=status.HTTP_201_CREATED)
        return Response({"error": _("Can not create Volume."), "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None, *args, **kwargs):
        volume = get_object_or_404(self.get_queryset(), pk=pk, user=request.user)
        serializer = self.get_serializer(volume, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"success": _("Volume updated.")}, status=status.HTTP_200_OK)
        return Response({"error": _("Can not update Volume"), "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None, *args, **kwargs):
        volume = get_object_or_404(self.get_queryset(), pk=pk, user=request.user)
        volume.delete()
        return Response({"success": _("Volume deleted.")}, status=status.HTTP_200_OK)


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
            service_item.save()
            transaction.on_commit(functools.partial(start_service.delay, str(deploy_item.id)))
            
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
                return Response({
                    "result": "error",
                    "detail": _("You can't stop service in (queued, deploying, stopping) modes.")
                    },
                    status=status.HTTP_409_CONFLICT 
                )
            
            service_item.status = SERVICE_STATUS_CHOICES.QUEUED
            service_item.save()
            transaction.on_commit(functools.partial(stop_service.delay, str(deploy_item.id)))
            
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
                "detail": _("Service with the ID not found.")
            }, 
            status=status.HTTP_404_NOT_FOUND
        )
    try:
        running = Container.container_is_running(service_item.name)
    
    except Exception:
        running = False    
    detail = _("service is running.") if running else _("service is not running.")
    return Response(
        {   "result": "success",
            "running": running,
            "detail": detail
        }, 
        status=status.HTTP_200_OK
    )
    
    