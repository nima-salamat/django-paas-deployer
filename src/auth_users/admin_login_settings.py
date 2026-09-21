"""
Admin LoginSettings API — singleton GET/PATCH with rule permissions.

Mounted at: /auth/api/admin/login-settings/
"""
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.response import Response
from rest_framework import status
from django.utils.translation import gettext as _

from .models import LoginSettings


EDITABLE_FIELDS = [
    "allow_username",
    "allow_email",
    "allow_phone",
    "require_password",
    "require_otp",
    "password_as_second_factor",
    "allow_auto_signup",
    "auto_activate_on_signup",
    "require_password_on_signup",
    "activate_after_successful_otp",
    "require_invite_for_signup",
    "allow_username_recovery",
    "recovery_via_email",
    "recovery_via_phone",
    "allow_password_recovery",
    "password_recovery_via_email",
    "password_recovery_via_phone",
    "require_confirm_password",
    "min_password_length",
    "allow_login",
    "custom_login_closed_title",
    "custom_login_closed_message",
    "otp_length",
    "otp_expire_minutes",
    "otp_max_attempts",
]


def _user_rules(user) -> list:
    try:
        return list(user.rule.rules or [])
    except Exception:
        return []


def _user_has_rule(user, code: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return code in _user_rules(user)


def serialize_settings(s: LoginSettings) -> dict:
    out = {}
    for f in EDITABLE_FIELDS:
        if hasattr(s, f):
            out[f] = getattr(s, f)
    return out


class HasLoginSettingsView(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        if u.is_superuser:
            return True
        if not u.is_staff:
            return False
        return _user_has_rule(u, "login_settings.view") or _user_has_rule(u, "login_settings.manage")


class HasLoginSettingsManage(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        if u.is_superuser:
            return True
        if not u.is_staff:
            return False
        return _user_has_rule(u, "login_settings.manage")


class AdminLoginSettingsAPIView(APIView):
    authentication_classes = [JWTAuthentication]

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT"):
            return [IsAuthenticated(), HasLoginSettingsManage()]
        return [IsAuthenticated(), HasLoginSettingsView()]

    def get(self, request):
        s = LoginSettings.get_solo()
        return Response({"success": True, "data": serialize_settings(s)})

    def patch(self, request):
        s = LoginSettings.get_solo()
        data = request.data or {}
        changed = []
        int_fields = {
            "min_password_length",
            "otp_length",
            "otp_expire_minutes",
            "otp_max_attempts",
        }
        text_fields = {"custom_login_closed_title", "custom_login_closed_message"}

        for field in EDITABLE_FIELDS:
            if field not in data or not hasattr(s, field):
                continue
            val = data[field]
            if field in int_fields:
                try:
                    val = int(val)
                except (TypeError, ValueError):
                    return Response(
                        {"success": False, "message": _(f"Invalid integer for {field}")},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if val < 1:
                    return Response(
                        {"success": False, "message": _(f"{field} must be >= 1")},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            elif field in text_fields:
                val = str(val or "")
            else:
                val = bool(val)

            if getattr(s, field) != val:
                setattr(s, field, val)
                changed.append(field)

        if changed:
            update_fields = list(changed)
            if hasattr(s, "updated_at"):
                update_fields.append("updated_at")
            s.save(update_fields=update_fields)

        return Response({
            "success": True,
            "message": _("Login settings updated."),
            "data": serialize_settings(s),
            "changed": changed,
        })
