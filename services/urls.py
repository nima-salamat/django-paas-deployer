from django.urls import path
from rest_framework.routers import DefaultRouter
from services.apis import (
    ServiceViewSet,
    PrivateNetworkViewSet,
    VolumeViewSet,
    start_service_apiview,
    stop_service_apiview
)
router = DefaultRouter()
router.register(r'service', ServiceViewSet, basename='service')
router.register(r'networks', PrivateNetworkViewSet, basename='private-network')
router.register(r'volume', VolumeViewSet, basename='volume')

urlpatterns = router.urls + [
    path("start_service/", start_service_apiview, name="start_service"),
    path("stop_service/", stop_service_apiview, name="stop_service")
    
]
