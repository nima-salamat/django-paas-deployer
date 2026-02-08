from django.urls import path
from .apis import DeployViewSet, deploy_name_is_available, start_container, stop_container

urlpatterns = [
    path('', DeployViewSet.as_view({'get': 'list', 'post': 'create'}), name='deploy-list'),
    path('<uuid:pk>/', DeployViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'}), name='deploy-detail'),
    path('name_is_available/', deploy_name_is_available, name="deploy_name_is_available"),
    path("start_container/", start_container, name="start_container"),
    path("stop_container/", stop_container, name="stop_container")

]

