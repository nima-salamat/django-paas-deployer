from django.urls import path

from .apis import (
    UserAPIView,
    PasswordStatusAPIView,
    SetPasswordAPIView,
    ChangePasswordAPIView,
    RemovePasswordAPIView,
)
from . import admin_apis
from . import admin_tables_api

urlpatterns = [
    path("user/", UserAPIView.as_view(), name="user_api"),
    path("password-status/", PasswordStatusAPIView.as_view(), name="password_status"),
    path("set-password/", SetPasswordAPIView.as_view(), name="set_password"),
    path("change-password/", ChangePasswordAPIView.as_view(), name="change_password"),
    path("remove-password/", RemovePasswordAPIView.as_view(), name="remove_password"),
    # Admin panel
    path("admin/permissions/", admin_apis.AdminPermissionCatalogAPIView.as_view(), name="admin_permissions"),
    path("admin/me/permissions/", admin_apis.MePermissionsAPIView.as_view(), name="admin_me_permissions"),
    path("admin/users/", admin_apis.AdminUserListAPIView.as_view(), name="admin_users"),
    path("admin/users/<int:pk>/", admin_apis.AdminUserDetailAPIView.as_view(), name="admin_user_detail"),
    path("admin/users/<int:pk>/rules/", admin_apis.AdminUserRulesAPIView.as_view(), name="admin_user_rules"),
    # Tables browser (NEW)
    path("admin/tables/", admin_tables_api.AdminTableListView.as_view(), name="admin_tables_list"),
    path("admin/tables/<str:model_key>/", admin_tables_api.AdminTableRowsView.as_view(), name="admin_table_rows"),
    path("admin/tables/<str:model_key>/<str:pk>/", admin_tables_api.AdminTableRowView.as_view(), name="admin_table_row"),
]
