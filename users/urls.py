from django.urls import path, include
from .apis import UserAPIView, ProfileViewSet, PasswordViewSet

urlpatterns = [
    path("api/user/", UserAPIView.as_view(), name="user_api"),
    path("api/profile/list/", ProfileViewSet.as_view({"post":"list","get":"list"}), name="profile_list"),
    path("api/profile/order/", ProfileViewSet.as_view({"post":"order"}), name="profile_order"),
    path("api/profile/delete/", ProfileViewSet.as_view({"post":"delete"}), name="profile_order"),
    path("api/profile/set/", ProfileViewSet.as_view({"post":"set"}), name="profile_order"),
    path("api/password/set/", PasswordViewSet.as_view({"post": "set"}), name="set_password"),
    path("api/password/delete/", PasswordViewSet.as_view({"post": "delete"}), name="delete_password"),
    path("api/plans/", include('plans.urls'), name="plans_api"),
    path("plans/", include("plans.html_urls"), name="plans_html")
]