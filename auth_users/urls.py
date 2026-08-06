from django.urls import path
from rest_framework_simplejwt import views as jwt_views

from .apis import (
    LoginSettingsAPIView,
    StartAuthAPIView,
    ValidateOTPAPIView,
    FinalAuthAPIView,
    SetPasswordAPIView,
    RecoveryRequestAPIView,
    RecoveryConfirmAPIView,
    ValidateToken,
    # legacy aliases
    LoginAPIView,
    SignupOrLoginAPIView,
    AuthAPIView,
    ValidateAPIView,
)

urlpatterns = [
    # ---- New clean endpoints ----
    path("api/settings/", LoginSettingsAPIView.as_view(), name="login_settings"),
    path("api/authentication/", StartAuthAPIView.as_view(), name="start_auth"),
    path("api/login/validate/", ValidateOTPAPIView.as_view(), name="validate_otp"),
    path("api/login/token/", FinalAuthAPIView.as_view(), name="final_auth"),
    path("api/set-password/", SetPasswordAPIView.as_view(), name="set_password"),
    path("api/recovery/request/", RecoveryRequestAPIView.as_view(), name="recovery_request"),
    path("api/recovery/confirm/", RecoveryConfirmAPIView.as_view(), name="recovery_confirm"),
    path("api/validateToken/", ValidateToken.as_view(), name="validate_token"),

    # JWT refresh / verify
    path("api/login/token/refresh", jwt_views.TokenRefreshView.as_view(), name="token_refresh"),
    path("api/login/token/verify", jwt_views.TokenVerifyView.as_view(), name="token_verify"),

    # ---- Legacy aliases (same views) ----
    path("api/login/", LoginAPIView.as_view(), name="login"),
    path("api/signup/", SignupOrLoginAPIView.as_view(), name="signup"),
]
