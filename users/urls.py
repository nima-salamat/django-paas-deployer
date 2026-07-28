from django.urls import path, include
from .apis import (
    UserAPIView,
    ProfileViewSet,
    PasswordStatusAPIView,
    SetPasswordAPIView,
    ChangePasswordAPIView,
    RemovePasswordAPIView,
)

urlpatterns = [
    path("user/", UserAPIView.as_view(), name="user_api"),
    path("profile/list/", ProfileViewSet.as_view({"post":"list","get":"list"}), name="profile_list"),
    path("profile/order/", ProfileViewSet.as_view({"post":"order"}), name="profile_order"),
    path("profile/delete/", ProfileViewSet.as_view({"post":"delete"}), name="profile_delete"),
    path("profile/set/", ProfileViewSet.as_view({"post":"set"}), name="profile_set"),
    path("password/status/", PasswordStatusAPIView.as_view(), name="password_status"),
    path("password/set/", SetPasswordAPIView.as_view(), name="set_password"),
    path("password/change/", ChangePasswordAPIView.as_view(), name="change_password"),
    path("password/remove/", RemovePasswordAPIView.as_view(), name="remove_password"),
    path("plans/", include('plans.urls'), name="plans_api"),
    path("plans/", include("plans.html_urls"), name="plans_html")
]