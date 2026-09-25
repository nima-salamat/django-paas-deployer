from rest_framework_simplejwt.views import TokenRefreshView

from .token_serializers import SessionTokenRefreshSerializer


class SessionTokenRefreshView(TokenRefreshView):
    serializer_class = SessionTokenRefreshSerializer
