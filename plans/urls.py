from django.urls import path
from .apis import PlanViewSet, PlatformPlans


urlpatterns = [
    path('plans/', PlanViewSet.as_view({'get': 'list', 'post': 'create'}), name='plan-list'),
    path('plans/<uuid:pk>/', PlanViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'update', 'delete': 'destroy'}), name='plan-detail'),
    path("platforms/", PlatformPlans.as_view(), name="platform_plans"),
]
