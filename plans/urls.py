from django.urls import path
from .apis import PlanViewSet


urlpatterns = [
    path('plans/', PlanViewSet.as_view({'get': 'list', 'post': 'create'}), name='plan-list'),
    path('plans/<uuid:pk>/', PlanViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'update', 'delete': 'destroy'}), name='plan-detail'),
]
