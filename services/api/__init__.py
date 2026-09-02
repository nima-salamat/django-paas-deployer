"""services API package."""
from .user_services import ServiceViewSet, PrivateNetworkViewSet, VolumeViewSet
from .volume_files import (
    volume_files_apiview, volume_download_apiview, purge_service_runtime_apiview,
)
from .runtime import (
    service_logs_apiview, service_logs_export_apiview, start_service_apiview, stop_service_apiview,
    force_cancel_deploy_apiview, service_status_apiview, restart_service_apiview,
)
from .admin_services import (
    AdminServiceViewSet, AdminPrivateNetworkViewSet, AdminVolumeViewSet,
    admin_start_service_apiview, admin_stop_service_apiview,
    admin_purge_service_runtime_apiview,
)
from .sharing import (
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
    service_access_info,
    user_can_access_service,
    record_share_event,
)

__all__ = [
    "ServiceViewSet", "PrivateNetworkViewSet", "VolumeViewSet",
    "volume_files_apiview", "volume_download_apiview", "purge_service_runtime_apiview",
    "service_logs_apiview", "start_service_apiview", "stop_service_apiview",
    "force_cancel_deploy_apiview", "service_status_apiview", "restart_service_apiview",
    "AdminServiceViewSet", "AdminPrivateNetworkViewSet", "AdminVolumeViewSet",
    "admin_start_service_apiview", "admin_stop_service_apiview",
    "admin_purge_service_runtime_apiview",
    "list_my_services", "list_shared_services", "list_services_unified",
    "create_share", "share_detail", "share_permissions", "share_events",
    "shares_for_group",
    "leave_share",
    "share_presets",
    "share_members",
    "service_access_info",
    "user_can_access_service", "record_share_event",
]
