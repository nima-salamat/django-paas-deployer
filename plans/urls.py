from django.urls import path
from .apis import PlanAdminViewSet, PlatformPlansAPIView, PlansApiView, PlanApplyAPIView

urlpatterns = [
    # Admin CRUD (rule-based: plans.view / plans.manage)
    # Full paths under root include: /plans/admin/plans/ ...
    path(
        "admin/plans/",
        PlanAdminViewSet.as_view({"get": "list", "post": "create"}),
        name="admin-plan-list",
    ),
    path(
        "admin/plans/<uuid:pk>/",
        PlanAdminViewSet.as_view({
            "get": "retrieve",
            "put": "update",
            "patch": "update",
            "delete": "destroy",
        }),
        name="admin-plan-detail",
    ),
    # Public / user-facing
    path("platforms/", PlatformPlansAPIView.as_view(), name="platform_plans"),
    path("", PlansApiView.as_view(), name="plans_api"),
    path("plans/<uuid:planId>/apply/", PlanApplyAPIView.as_view(), name="plan-apply"),
]
