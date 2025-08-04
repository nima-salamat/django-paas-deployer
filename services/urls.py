from django.urls import path
from .apis import ServiceViewSet

urlpatterns = [
    path('', ServiceViewSet.as_view({"get": "list", "post": "create"}), name='service-list'),
    path('<pk>/', ServiceViewSet.as_view({"patch": "update", "delete": "destroy"}), name='service-detail'),
]
