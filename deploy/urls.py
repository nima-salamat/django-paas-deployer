from django.urls import path
from .apis import DeployViewSet

urlpatterns = [
    path('', DeployViewSet.as_view({'get': 'list', 'post': 'create'}), name='deploy-list'),
    path('<int:pk>/', DeployViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='deploy-detail'),
]

