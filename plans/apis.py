from .models import Plan
from .serializers import PlanSerializer, UnauthorizedPlanSerializer
from rest_framework.viewsets import ViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from core.global_settings import config
from core.utils import is_valid_uuid4
from django.utils.translation import gettext as _


class PlanAdminViewSet(ViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminUser]

    # def get_permissions(self):
    #     if self.request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
    #         # Only admin users can create, update, delete
    #         return [IsAuthenticated(), IsAdminUser()]
    #     return [IsAuthenticated()]
    
    def list(self, request):
        plan = Plan.objects.all()
        serializer = PlanSerializer(plan, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def retrieve(self, request, pk=None):
        try:
            plan = Plan.objects.get(pk=pk)
        except Plan.DoesNotExist:
            return Response({"error": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        serializer = PlanSerializer(plan)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request):
        serializer = PlanSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        try:
            plan = Plan.objects.get(pk=pk)
        except Plan.DoesNotExist:
            return Response({"error": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        serializer = PlanSerializer(plan, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        try:
            plan = Plan.objects.get(pk=pk)
        except Plan.DoesNotExist:
            return Response({"error": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        plan.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    
class PlatformPlansAPIView(APIView):
    def get(self, request):
        return Response(data=config.PLATFORM_CHOICES, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        platform = data.get("platform")
        query_argument = ""
        if platform:
            for i,j in config.PLATFORM_CHOICES:
                if platform in (i,j):
                    query_argument = i
                    
        if not query_argument:
            return Response(data={"error":_("Incorrect platform.")}, status=status.HTTP_400_BAD_REQUEST)
            
        plans = Plan.objects.filter(platform=query_argument)
        if not plans.exists():
            return Response(data={"error":_("There is not such plans.")}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = PlanSerializer(plans, many=True)
        
        return Response(data=serializer.data, status=status.HTTP_200_OK)

class PlansApiView(APIView):
    def get(self, request):
        """
        GET /plans/ 
        GET /plans/?id=1,2,3 
        GET /plans/?id=1   
        """
        ids = request.query_params.get("id", "")
        if not ids:
            plans = Plan.objects.all().order_by("platform")
        else:
            if "," in ids:
                all_ids = [i for i in ids.split(",") if i and is_valid_uuid4(i)]
                        
                plans = Plan.objects.filter(pk__in=all_ids).order_by("platform")
                if not plans.exists():
                    return Response(data={"error": _("Plan not found.")}, status=status.HTTP_404_NOT_FOUND)

            else:
                if not is_valid_uuid4(ids):
                    return Response(
                        data={
                            "error": _("Invalid UUID format."),
                            "details": _("Please provide a valid UUID v4 format."),
                            "received_id": ids
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                try:
                    plan = Plan.objects.get(pk=ids)
                except Plan.DoesNotExist:
                    return Response(data={_("error"): _("Plan not found.")}, status=status.HTTP_404_NOT_FOUND)
        
                serializer = PlanSerializer(plan)
                return Response(data=serializer.data, status=status.HTTP_200_OK)
                

        paginator = PageNumberPagination()
        paginated_plans = paginator.paginate_queryset(plans, request)
        serializer = PlanSerializer(paginated_plans, many=True)
        return paginator.get_paginated_response(serializer.data)


class PlanApplyAPIView(APIView):
    """
    POST /plans/<planId>/apply
    Body: { "target_type": "service", "target_id": "<uuid>", "applyImmediately": true }
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, planId=None):
        from django.shortcuts import get_object_or_404
        from services.models import Service
        from deployments.celery.tasks import deploy as start_service
        from core.global_settings.config import SERVICE_STATUS_CHOICES
        from django.db import transaction

        try:
            plan = Plan.objects.get(pk=planId)
        except Plan.DoesNotExist:
            return Response({"error": _('Plan not found.')}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        target_type = data.get('target_type')
        target_id = data.get('target_id')
        apply_immediately = bool(data.get('applyImmediately'))

        if target_type != 'service' or not target_id:
            return Response({"error": _('Invalid target_type or missing target_id.')}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                service = Service.objects.select_for_update().get(pk=target_id, user=request.user)
                # Assign the plan
                service.plan = plan
                service.save()

                # Optionally trigger redeploy if requested and a deploy is selected
                if apply_immediately:
                    deploy_item = service.selected_deploy
                    if deploy_item is None:
                        return Response({"result": "error", "detail": _('Service has no selected deploy to apply.')}, status=status.HTTP_409_CONFLICT)

                    if service.status in (
                        SERVICE_STATUS_CHOICES.QUEUED,
                        SERVICE_STATUS_CHOICES.DEPLOYING,
                        SERVICE_STATUS_CHOICES.STOPPING,
                    ):
                        return Response({"result": "error", "detail": _('Service cannot be redeployed in its current status.')}, status=status.HTTP_409_CONFLICT)

                    service.status = SERVICE_STATUS_CHOICES.QUEUED
                    service.save()
                    transaction.on_commit(lambda: start_service.delay(str(deploy_item.id)))

        except Service.DoesNotExist:
            return Response({"error": _('Service not found or not owned by user.')}, status=status.HTTP_404_NOT_FOUND)

        return Response({"result": "success", "detail": _('Plan applied to target.')}, status=status.HTTP_202_ACCEPTED)