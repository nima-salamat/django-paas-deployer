from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .token_serializers import (
    SessionTokenRefreshSerializer,
    SessionTokenVerifySerializer,
)


class SessionTokenRefreshView(TokenRefreshView):
    serializer_class = SessionTokenRefreshSerializer


class SessionTokenVerifyView(TokenVerifyView):
    serializer_class = SessionTokenVerifySerializer
