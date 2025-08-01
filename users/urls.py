from django.urls import path
from .apis import UserAPIView, ProfileViewSet

urlpatterns = [
    path("api/user/", UserAPIView.as_view(), name="user_api"),
    path("api/profile/list/", ProfileViewSet.as_view({"post":"list","get":"list"}), name="profile_list"),
    path("api/profile/order/", ProfileViewSet.as_view({"post":"order"}), name="profile_order"),
    path("api/profile/delete/", ProfileViewSet.as_view({"post":"delete"}), name="profile_order"),
    path("api/profile/set/", ProfileViewSet.as_view({"post":"set"}), name="profile_order"),
]