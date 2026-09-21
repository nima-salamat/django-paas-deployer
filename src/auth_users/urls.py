from django.urls import path
from rest_framework_simplejwt import views as jwt_views
from .admin_login_settings import AdminLoginSettingsAPIView

from .apis import (
    LoginSettingsAPIView,
    StartAuthAPIView,
    ValidateOTPAPIView,
    FinalAuthAPIView,
    SetPasswordAPIView,
    RecoveryRequestAPIView,
    RecoveryConfirmAPIView,
    PasswordRecoveryRequestAPIView,
    PasswordRecoveryConfirmAPIView,
    ValidateToken,
    InviteValidateAPIView,
    InviteCreateAPIView,
    InviteListAPIView,
    InviteDeactivateAPIView,
    AdminAuthCodeListAPIView,
    AdminAuthCodeDeleteAPIView,
    AdminAuthCodePurgeAPIView,
    # legacy aliases
    LoginAPIView,
    SignupOrLoginAPIView,
    AuthAPIView,
    ValidateAPIView,
)

urlpatterns = [
    # ---- Settings ----
    path("api/settings/", LoginSettingsAPIView.as_view(), name="login_settings"),
    path("api/admin/login-settings/", AdminLoginSettingsAPIView.as_view(), name="admin_login_settings"),

    # ---- Auth flow ----
    path("api/authentication/", StartAuthAPIView.as_view(), name="start_auth"),
    path("api/login/validate/", ValidateOTPAPIView.as_view(), name="validate_otp"),
    path("api/login/token/", FinalAuthAPIView.as_view(), name="final_auth"),
    path("api/set-password/", SetPasswordAPIView.as_view(), name="set_password"),

    # ---- Username recovery ----
    path("api/recovery/request/", RecoveryRequestAPIView.as_view(), name="recovery_request"),
    path("api/recovery/confirm/", RecoveryConfirmAPIView.as_view(), name="recovery_confirm"),

    # ---- Password recovery (Forgot Password) ----
    path("api/password-recovery/request/", PasswordRecoveryRequestAPIView.as_view(), name="password_recovery_request"),
    path("api/password-recovery/confirm/", PasswordRecoveryConfirmAPIView.as_view(), name="password_recovery_confirm"),

    # ---- Invite system ----
    path("api/invite/validate/", InviteValidateAPIView.as_view(), name="invite_validate"),
    path("api/invite/create/", InviteCreateAPIView.as_view(), name="invite_create"),
    path("api/invite/list/", InviteListAPIView.as_view(), name="invite_list"),
    path("api/invite/deactivate/", InviteDeactivateAPIView.as_view(), name="invite_deactivate"),

    # ---- Token check ----
    path("api/admin/auth-codes/", AdminAuthCodeListAPIView.as_view(), name="admin_auth_codes"),
    path("api/admin/auth-codes/purge/", AdminAuthCodePurgeAPIView.as_view(), name="admin_auth_codes_purge"),
    path("api/admin/auth-codes/<int:pk>/", AdminAuthCodeDeleteAPIView.as_view(), name="admin_auth_code_delete"),
    path("api/validateToken/", ValidateToken.as_view(), name="validate_token"),

    # JWT — register BOTH with and without trailing slash to avoid POST redirect issues
    path("api/login/token/refresh", jwt_views.TokenRefreshView.as_view(), name="token_refresh"),
    path("api/login/token/refresh/", jwt_views.TokenRefreshView.as_view(), name="token_refresh_slash"),
    path("api/login/token/verify", jwt_views.TokenVerifyView.as_view(), name="token_verify"),
    path("api/login/token/verify/", jwt_views.TokenVerifyView.as_view(), name="token_verify_slash"),

    # Legacy aliases
    path("api/login/", LoginAPIView.as_view(), name="login"),
    path("api/signup/", SignupOrLoginAPIView.as_view(), name="signup"),
]
