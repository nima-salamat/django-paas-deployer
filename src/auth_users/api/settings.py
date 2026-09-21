import logging
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone

from users.serializers import CreateUserSerializer
from ..models import LoginSettings, AuthCode, InviteLink, InviteUsage
from ..services import (
    get_tokens_for_user,
    resolve_user_from_identifiers,
    extract_contact,
    send_otp,
    validate_required_identifiers,
    can_create_user,
    resolve_invite,
)

User = get_user_model()
logger = logging.getLogger("auth_users.apis")


def err(msg, http_status=status.HTTP_400_BAD_REQUEST, extra=None):
    body = {"message": msg, "success": False}
    if extra:
        body.update(extra)
    return Response(body, status=http_status)


def ok(msg, data=None, http_status=status.HTTP_200_OK):
    body = {"message": msg, "success": True}
    if data:
        body.update(data)
    return Response(body, status=http_status)


# ---------------------------------------------------------------------------
# Public endpoint: current login settings
# ---------------------------------------------------------------------------
class LoginSettingsAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        s = LoginSettings.get_solo()
        return ok(
            _("success::settings"),
            {
                "settings": {
                    "allow_username": s.allow_username,
                    "allow_email": s.allow_email,
                    "allow_phone": s.allow_phone,
                    "require_password": s.require_password,
                    "require_otp": s.require_otp,
                    "password_as_second_factor": s.password_as_second_factor,
                    "allow_auto_signup": s.allow_auto_signup,
                    "auto_activate_on_signup": s.auto_activate_on_signup,
                    "require_password_on_signup": s.require_password_on_signup,
                    "activate_after_successful_otp": s.activate_after_successful_otp,
                    "require_invite_for_signup": s.require_invite_for_signup,
                    "allow_username_recovery": s.allow_username_recovery,
                    "recovery_via_email": s.recovery_via_email,
                    "recovery_via_phone": s.recovery_via_phone,
                    "allow_password_recovery": s.allow_password_recovery,
                    "password_recovery_via_email": s.password_recovery_via_email,
                    "password_recovery_via_phone": s.password_recovery_via_phone,
                    "require_confirm_password": s.require_confirm_password,
                    "min_password_length": s.min_password_length,
                    "allow_login": s.allow_login,
                    "custom_login_closed_title": s.custom_login_closed_title or "Login temporarily unavailable",
                    "custom_login_closed_message": s.custom_login_closed_message or "",
                    "otp_length": s.otp_length,
                    "otp_expire_minutes": s.otp_expire_minutes,
                }
            },
        )


# ---------------------------------------------------------------------------
# Invite validation (public – frontend checks before showing form)
# GET /api/invite/validate/?token=xxx
# ---------------------------------------------------------------------------
