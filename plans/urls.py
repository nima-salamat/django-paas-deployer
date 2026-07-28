from django.urls import path
from .apis import PlanAdminViewSet, PlatformPlansAPIView, PlansApiView, PlanApplyAPIView


urlpatterns = [
    path('plans/admin/', PlanAdminViewSet.as_view({'get': 'list', 'post': 'create'}), name='plan-list'),
    path('plans/admin/<uuid:pk>/', PlanAdminViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'update', 'delete': 'destroy'}), name='plan-detail'),
    path("platforms/", PlatformPlansAPIView.as_view(), name="platform_plans"),
    path("", PlansApiView.as_view(), name="plans_api"),
    path('plans/<uuid:planId>/apply/', PlanApplyAPIView.as_view(), name='plan-apply'),
]
