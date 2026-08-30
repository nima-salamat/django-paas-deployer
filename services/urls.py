from django.urls import path
from rest_framework.routers import DefaultRouter
from services.apis import (
    ServiceViewSet,
    PrivateNetworkViewSet,
    VolumeViewSet,
    AdminServiceViewSet,
    AdminPrivateNetworkViewSet,
    AdminVolumeViewSet,
    start_service_apiview,
    stop_service_apiview,
    force_cancel_deploy_apiview,
    service_status_apiview,
    restart_service_apiview,
    service_logs_apiview,
    volume_files_apiview,
    volume_download_apiview,
    purge_service_runtime_apiview,
    admin_start_service_apiview,
    admin_stop_service_apiview,
    admin_purge_service_runtime_apiview,
    # Sharing
    list_my_services,
    list_shared_services,
    list_services_unified,
    create_share,
    share_detail,
    share_permissions,
    share_events,
    shares_for_group,
    leave_share,
    share_presets,
    share_members,
)

# ---------------------------------------------------------------------------
# User-facing routes — ALWAYS scoped to request.user (even for staff)
# ---------------------------------------------------------------------------
router = DefaultRouter()
router.register(r"service", ServiceViewSet, basename="service")
router.register(r"networks", PrivateNetworkViewSet, basename="private-network")
router.register(r"volume", VolumeViewSet, basename="volume")

# ---------------------------------------------------------------------------
# Admin panel routes — require services.view / services.manage rules
# ---------------------------------------------------------------------------
admin_router = DefaultRouter()
admin_router.register(r"admin/services", AdminServiceViewSet, basename="admin-service")
admin_router.register(r"admin/networks", AdminPrivateNetworkViewSet, basename="admin-network")
admin_router.register(r"admin/volumes", AdminVolumeViewSet, basename="admin-volume")

urlpatterns = (
    router.urls
    + admin_router.urls
    + [
        path("start_service/", start_service_apiview, name="start_service"),
        path("stop_service/", stop_service_apiview, name="stop_service"),
        path("restart_service/", restart_service_apiview, name="restart_service"),
        path("force_cancel_deploy/", force_cancel_deploy_apiview, name="force_cancel_deploy"),
        path("purge_service_runtime/", purge_service_runtime_apiview, name="purge_service_runtime"),
        # Admin cross-user runtime actions
        path("admin/start_service/", admin_start_service_apiview, name="admin_start_service"),
        path("admin/stop_service/", admin_stop_service_apiview, name="admin_stop_service"),
        path("admin/purge_service_runtime/", admin_purge_service_runtime_apiview, name="admin_purge_service_runtime"),
        path("service_status/", service_status_apiview, name="service_status"),
        path("service/<uuid:pk>/logs/", service_logs_apiview, name="service_logs"),
        path("volume/<uuid:pk>/files/", volume_files_apiview, name="volume_files"),
        path("volume/<uuid:pk>/download/", volume_download_apiview, name="volume_download"),
        # ------------------------------------------------------------------
        # Service Sharing
        # ------------------------------------------------------------------
        path("services/mine/", list_my_services, name="services_mine"),
        path("services/shared/", list_shared_services, name="services_shared"),
        path("services/unified/", list_services_unified, name="services_unified"),
        path("services/share/", create_share, name="services_share_create"),
        path("services/shares/<uuid:pk>/", share_detail, name="services_share_detail"),
        path("services/shares/<uuid:pk>/permissions/", share_permissions, name="services_share_permissions"),
        path("services/shares/<uuid:pk>/events/", share_events, name="services_share_events"),
        path("services/groups/<int:group_id>/shares/", shares_for_group, name="services_group_shares"),
        path("services/shares/<uuid:pk>/leave/", leave_share, name="services_share_leave"),
        path("services/shares/<uuid:pk>/members/", share_members, name="services_share_members"),
        path("services/share-presets/", share_presets, name="services_share_presets"),
    ]
)
