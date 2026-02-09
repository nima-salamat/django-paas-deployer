from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from .models import Deploy
from services.models import Service
from .serializers import DeploySerializer
from deployments.tasks.deploy import deploy, stop



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
            serializer.save()
            return Response({"success": _("Deploy created.")}, status=status.HTTP_201_CREATED)
        return Response({"error": _("Can not deploy."), "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None, *args, **kwargs):
        deploy = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(deploy, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"success": _("Deploy updated.")}, status=status.HTTP_200_OK)
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



@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def start_container(request):
    deploy_id = request.data.get("deploy_id", "")
    
    if Deploy.objects.filter(id=deploy_id).exists():
            deploy_item = Deploy.objects.prefetch_related("service").get(id=deploy_id)
            if deploy_item.service.user != request.user:
                    return Response({"result": "error", "detail": _("Only owner can run the service.")})
                
            for item in Deploy.objects.filter(service=deploy_item.service):
                if item.running:
                    return Response({"result": "error", "detail": _("Only one container can be in running mode.")})
                    
            deploy.delay(deploy_id)
            return Response({"result": "success", "detail": _("Deploy started.")})
    return Response({"result": "error", "detail": _("The deploy_id is invalid.")})
    

@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def stop_container(request):
    deploy_id = request.data.get("deploy_id", "")
    if Deploy.objects.filter(id=deploy_id).exists():
            deploy_item = Deploy.objects.prefetch_related("service").get(id=deploy_id)
            if deploy_item.service.user != request.user:
                    return Response({"result": "error", "detail": _("Only owner can stop the service.")})
            stop.delay(deploy_id)
            return Response({"result": "success", "detail": _("Deploy stopped.")})
    return Response({"result": "error", "detail": _("The deploy_id is invalid.")})
    
    

