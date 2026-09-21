from django.urls import path
from rest_framework.routers import DefaultRouter
from services.apis import VolumeViewSet, volume_files_apiview, volume_download_apiview

router = DefaultRouter()
router.register(r"", VolumeViewSet, basename="volume")

urlpatterns = router.urls + [
    path("<uuid:pk>/files/", volume_files_apiview, name="volume_files"),
    path("<uuid:pk>/download/", volume_download_apiview, name="volume_download"),
]
