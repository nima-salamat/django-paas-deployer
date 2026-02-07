from django.urls import path
from .apis import DeployViewSet, deploy_name_is_available

urlpatterns = [
    path('', DeployViewSet.as_view({'get': 'list', 'post': 'create'}), name='deploy-list'),
    path('<int:pk>/', DeployViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='deploy-detail'),
    path('name_is_available/', deploy_name_is_available, name="deploy_name_is_available")
]

