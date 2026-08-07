from django.urls import path
from core.apis_settings import (
    SystemSettingListAPIView,
    SystemSettingDetailAPIView,
    SystemSettingSeedAPIView,
)

urlpatterns = [
    path("settings/", SystemSettingListAPIView.as_view(), name="system-settings-list"),
    path(
        "settings/seed/",
        SystemSettingSeedAPIView.as_view(),
        name="system-settings-seed",
    ),
    path(
        "settings/<str:key>/",
        SystemSettingDetailAPIView.as_view(),
        name="system-settings-detail",
    ),
]
