from .models import Plan
from .serializers import PlanSerializer, UnauthorizedPlanSerializer
from rest_framework.viewsets import ViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated, BasePermission, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from core.global_settings import config
from core.utils import is_valid_uuid4
from django.utils.translation import gettext as _
from django.db.models import Q
from django.db import transaction


# ---------------------------------------------------------------------------
# Permission helpers (aligned with users.admin_apis Rule system)
# ---------------------------------------------------------------------------
def _user_rules(user) -> list:
    try:
        return list(user.rule.rules or [])
    except Exception:
        return []


def _user_has_rule(user, code: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return code in _user_rules(user)


class HasPlansViewRule(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        if u.is_superuser:
            return True
        if not u.is_staff:
            return False
        return _user_has_rule(u, "plans.view") or _user_has_rule(u, "plans.manage")


class HasPlansManageRule(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        if u.is_superuser:
            return True
        if not u.is_staff:
            return False
        return _user_has_rule(u, "plans.manage")


class PlanAdminPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class PlanAdminViewSet(ViewSet):
    """
    Admin CRUD for plans.

    GET list/retrieve  → plans.view (or manage)
    POST/PUT/PATCH/DELETE → plans.manage
    Superuser bypasses all checks.
    """
    authentication_classes = [JWTAuthentication]
    pagination_class = PlanAdminPagination

    def get_permissions(self):
        if self.action in ("create", "update", "destroy"):
            return [IsAuthenticated(), HasPlansManageRule()]
        return [IsAuthenticated(), HasPlansViewRule()]

    def get_authenticators(self):
        return [auth() for auth in self.authentication_classes]

    def list(self, request):
        from core.app_cache import cache_get, cache_set, plan_admin_list_key, PLAN_TTL
        params = {k: (request.query_params.get(k) or "") for k in ("q", "q_search", "platform", "plan_type", "page", "page_size")}
        key = plan_admin_list_key(params)
        cached = cache_get(key)
        if cached is not None:
            return Response(cached)
        qs = Plan.objects.all().order_by("name", "platform")
        q = (params.get("q") or params.get("q_search") or "").strip()
        platform = (params.get("platform") or "").strip()
        plan_type = (params.get("plan_type") or "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(platform__icontains=q))
        if platform:
            qs = qs.filter(platform=platform)
        if plan_type:
            qs = qs.filter(plan_type=plan_type)
        paginator = PlanAdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = PlanSerializer(page, many=True)
        resp = paginator.get_paginated_response(serializer.data)
        try:
            cache_set(key, resp.data, PLAN_TTL)
        except Exception:
            pass
        return resp

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
            try:
                from core.app_cache import invalidate_all_plans
                invalidate_all_plans()
            except Exception:
                pass
            return Response(
                {"success": True, "message": _("Plan created."), "data": serializer.data},
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def update(self, request, pk=None):
        try:
            plan = Plan.objects.get(pk=pk)
        except Plan.DoesNotExist:
            return Response({"error": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        serializer = PlanSerializer(plan, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            try:
                from core.app_cache import invalidate_all_plans
                invalidate_all_plans()
            except Exception:
                pass
            return Response(
                {"success": True, "message": _("Plan updated."), "data": serializer.data}
            )
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def destroy(self, request, pk=None):
        try:
            plan = Plan.objects.get(pk=pk)
        except Plan.DoesNotExist:
            return Response({"error": _("Not found.")}, status=status.HTTP_404_NOT_FOUND)
        try:
            from services.models import Service
            if Service.objects.filter(plan=plan).exists():
                return Response(
                    {
                        "success": False,
                        "message": _("Cannot delete: plan is still assigned to one or more services."),
                    },
                    status=status.HTTP_409_CONFLICT,
                )
        except Exception:
            pass
        plan.delete()
        try:
            from core.app_cache import invalidate_all_plans
            invalidate_all_plans()
        except Exception:
            pass
        return Response(
            {"success": True, "message": _("Plan deleted.")},
            status=status.HTTP_200_OK,
        )


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
        from core.app_cache import cache_get, cache_set, plan_list_key, plan_detail_key, PLAN_TTL
        ids = request.query_params.get("id", "")
        if not ids:
            key = plan_list_key({"page": request.query_params.get("page") or "1"})
            cached = cache_get(key)
            if cached is not None:
                return Response(cached)
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
        resp = paginator.get_paginated_response(serializer.data)
        try:
            from core.app_cache import cache_set, plan_list_key, PLAN_TTL
            cache_set(plan_list_key({"page": request.query_params.get("page") or "1"}), resp.data, PLAN_TTL)
        except Exception:
            pass
        return resp


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