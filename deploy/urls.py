from django.urls import path
from .apis import (
    DeployViewSet,
    deploy_name_is_available,
    set_deploy_apiview,
    unset_deploy_apiview
)

urlpatterns = [
    path('', DeployViewSet.as_view({'get': 'list', 'post': 'create'}), name='deploy-list'),
    path('<uuid:pk>/', DeployViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='deploy-detail'),
    path('name_is_available/', deploy_name_is_available, name="deploy_name_is_available"),
    path("set_deploy/", set_deploy_apiview, name="set_deploy"),
    path("unset_deploy/", unset_deploy_apiview, name="unset_deploy")

]

