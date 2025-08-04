from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from .models import Deploy
from .serializers import DeploySerializer
from services.models import Service


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
        page = self.paginate_queryset(self.get_queryset())
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            service_id = request.data.get("service")
            if not service_id or not Service.objects.filter(id=service_id, user=request.user).exists():
                return Response(
                    {"error": "Service must belong to the authenticated user."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"success": "Deploy created."}, status=status.HTTP_201_CREATED)
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None, *args, **kwargs):
        deploy = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(deploy, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"success": "Deploy updated."}, status=status.HTTP_200_OK)
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None, *args, **kwargs):
        deploy = get_object_or_404(self.get_queryset(), pk=pk)
        deploy.delete()
        return Response({"success": "Deploy deleted."}, status=status.HTTP_200_OK)
