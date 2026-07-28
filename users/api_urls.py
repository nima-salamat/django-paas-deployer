from django.urls import path

from .apis import (
    UserAPIView,
    PasswordStatusAPIView,
    SetPasswordAPIView,
    ChangePasswordAPIView,
    RemovePasswordAPIView,
)

urlpatterns = [
    path("user/", UserAPIView.as_view(), name="user_api"),
    path("password-status/", PasswordStatusAPIView.as_view(), name="password_status"),
    path("set-password/", SetPasswordAPIView.as_view(), name="set_password"),
    path("change-password/", ChangePasswordAPIView.as_view(), name="change_password"),
    path("remove-password/", RemovePasswordAPIView.as_view(), name="remove_password"),
]
