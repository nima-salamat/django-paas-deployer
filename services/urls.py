from django.urls import path
from .apis import ContainerViewSet, PrivateNetworkViewSet

urlpatterns = [
    path('', ContainerViewSet.as_view({"get": "list", "post": "create"}), name='service-list'),
    path('<pk>/', ContainerViewSet.as_view({"patch": "update", "delete": "destroy"}), name='service-detail'),
    path('networks/', PrivateNetworkViewSet.as_view({"get": "list", "post": "create"}), name='private-network-list'),
    path('networks/<pk>/', PrivateNetworkViewSet.as_view({"patch": "update", "delete": "destroy"}), name='private-network-detail'),
]
