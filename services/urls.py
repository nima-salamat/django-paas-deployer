from django.urls import path
from rest_framework.routers import DefaultRouter
from services.apis import (
    ServiceViewSet,
    PrivateNetworkViewSet,
    VolumeViewSet,
    start_service_apiview,
    stop_service_apiview,
    service_status_apiview,
    service_logs_apiview,
    volume_files_apiview,
    volume_download_apiview,
    purge_service_runtime_apiview,
)
router = DefaultRouter()
router.register(r'service', ServiceViewSet, basename='service')
router.register(r'networks', PrivateNetworkViewSet, basename='private-network')
router.register(r'volume', VolumeViewSet, basename='volume')

urlpatterns = router.urls + [
    path("start_service/", start_service_apiview, name="start_service"),
    path("stop_service/", stop_service_apiview, name="stop_service"),
    path("purge_service_runtime/", purge_service_runtime_apiview, name="purge_service_runtime"),
    path("service_status/", service_status_apiview, name="service_status"),
    path("service/<uuid:pk>/logs/", service_logs_apiview, name="service_logs"),
    path("volume/<uuid:pk>/files/", volume_files_apiview, name="volume_files"),
    path("volume/<uuid:pk>/download/", volume_download_apiview, name="volume_download"),
]
