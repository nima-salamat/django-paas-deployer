from django.urls import path
from .apis import ServiceViewSet, PrivateNetworkViewSet

urlpatterns = [
    path('', ServiceViewSet.as_view({"get": "list", "post": "create"}), name='service-list'),
    path('<pk>/', ServiceViewSet.as_view({"patch": "update", "delete": "destroy"}), name='service-detail'),
    path('networks/', PrivateNetworkViewSet.as_view({"get": "list", "post": "create"}), name='private-network-list'),
    path('networks/<pk>/', PrivateNetworkViewSet.as_view({"patch": "update", "delete": "destroy"}), name='private-network-detail'),
]
