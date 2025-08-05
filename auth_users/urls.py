from django.urls import path
from rest_framework_simplejwt import views as jwt_views
from .apis import LoginAPIView, ValidateAPIView, AuthAPIView, SignupView, SignupOrLoginAPIView

urlpatterns = [
    path("api/login/token/refresh", jwt_views.TokenVerifyView.as_view(), name="refresh_token"),
    path("api/login/token/", AuthAPIView.as_view(), name="create_token"),
    path("api/login/validate/", ValidateAPIView.as_view(), name="validate"),
    path("api/login/", LoginAPIView.as_view(), name="login"),
    path("api/signup/", SignupView.as_view(), name="signin"),
    path("api/authentication/", SignupOrLoginAPIView.as_view(), name="signin_or_login"),
]
