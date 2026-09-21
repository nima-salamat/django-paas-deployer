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
from ..models import LoginSettings, AuthCode, InviteLink, InviteUsage, LoginLog
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
class RecoveryRequestAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        settings = LoginSettings.get_solo()
        if not settings.allow_login:
            return err(
                settings.custom_login_closed_message
                or _("error::login is temporarily closed"),
                status.HTTP_403_FORBIDDEN,
            )

        if not settings.allow_username_recovery:
            return err(_("error::username recovery is disabled"), status.HTTP_403_FORBIDDEN)

        email = (request.data.get("email") or "").strip().lower()
        phone = (request.data.get("phone_number") or "").strip()

        if not email and not phone:
            return err(_("error::email or phone is required"))

        if email and not settings.recovery_via_email:
            return err(_("error::email recovery is disabled"))
        if phone and not settings.recovery_via_phone:
            return err(_("error::phone recovery is disabled"))

        q = Q()
        if email:
            q |= Q(email=email)
        if phone:
            q |= Q(phone_number=phone)
        users = User.objects.filter(q)
        if not users.exists():
            return ok(_("success::if the account exists a code was sent"))

        user = users.first()
        channel = "email" if email else "phone"
        contact = email or phone

        send_otp(
            user=user,
            contact=contact,
            channel=channel,
            purpose=AuthCode.PURPOSE_RECOVERY,
        )
        return ok(
            _("success::code sent"),
            {"channel": channel, "next_step": "recovery_otp"},
        )


class RecoveryConfirmAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        settings = LoginSettings.get_solo()
        if not settings.allow_login:
            return err(
                settings.custom_login_closed_message
                or _("error::login is temporarily closed"),
                status.HTTP_403_FORBIDDEN,
            )

        if not settings.allow_username_recovery:
            return err(_("error::username recovery is disabled"), status.HTTP_403_FORBIDDEN)

        email = (request.data.get("email") or "").strip().lower()
        phone = (request.data.get("phone_number") or "").strip()
        code = (request.data.get("code") or "").strip()

        if not code:
            return err(_("error::code is required"))
        if not email and not phone:
            return err(_("error::email or phone is required"))

        q = Q()
        if email:
            q |= Q(email=email)
        if phone:
            q |= Q(phone_number=phone)
        user = User.objects.filter(q).first()
        if not user:
            return err(_("error::invalid code or contact"))

        is_valid, instance = AuthCode.validate(
            user=user, code=code, purpose=AuthCode.PURPOSE_RECOVERY
        )
        if not is_valid:
            return err(_("error::code is incorrect or expired"))

        instance.consume()
        return ok(
            _("success::username recovered"),
            {
                "username": user.username,
                "email": user.email if settings.allow_email else None,
                "phone_number": getattr(user, "phone_number", None)
                if settings.allow_phone
                else None,
            },
        )



# ---------------------------------------------------------------------------
# Password recovery (Forgot Password)
# ---------------------------------------------------------------------------
class PasswordRecoveryRequestAPIView(APIView):
    """
    POST /api/password-recovery/request/
    Body: { "email": "..." }  or  { "phone_number": "..." }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        settings = LoginSettings.get_solo()
        if not settings.allow_login:
            return err(
                settings.custom_login_closed_message
                or _("error::login is temporarily closed"),
                status.HTTP_403_FORBIDDEN,
            )
        if not settings.allow_password_recovery:
            return err(_("error::password recovery is disabled"), status.HTTP_403_FORBIDDEN)

        email = (request.data.get("email") or "").strip().lower()
        phone = (request.data.get("phone_number") or "").strip()

        if not email and not phone:
            return err(_("error::email or phone is required"))

        if email and not settings.password_recovery_via_email:
            return err(_("error::email password recovery is disabled"))
        if phone and not settings.password_recovery_via_phone:
            return err(_("error::phone password recovery is disabled"))

        q = Q()
        if email:
            q |= Q(email=email)
        if phone:
            q |= Q(phone_number=phone)
        users = User.objects.filter(q)
        if not users.exists():
            return ok(_("success::if the account exists a code was sent"))

        user = users.first()
        channel = "email" if email else "phone"
        contact = email or phone

        send_otp(
            user=user,
            contact=contact,
            channel=channel,
            purpose=AuthCode.PURPOSE_PASSWORD_RESET,
        )
        return ok(
            _("success::code sent"),
            {"channel": channel, "next_step": "password_recovery_otp"},
        )


class PasswordRecoveryConfirmAPIView(APIView):
    """
    POST /api/password-recovery/confirm/
    Body: email/phone_number + code + password + password_confirm
    """
    permission_classes = [AllowAny]

    def post(self, request):
        settings = LoginSettings.get_solo()
        if not settings.allow_login:
            return err(
                settings.custom_login_closed_message
                or _("error::login is temporarily closed"),
                status.HTTP_403_FORBIDDEN,
            )
        if not settings.allow_password_recovery:
            return err(_("error::password recovery is disabled"), status.HTTP_403_FORBIDDEN)

        data = {k: (v or "").strip() if isinstance(v, str) else v for k, v in request.data.items()}
        email = (data.get("email") or "").strip().lower()
        phone = (data.get("phone_number") or "").strip()
        code = (data.get("code") or "").strip()
        password = data.get("password", "")
        password_confirm = data.get("password_confirm", data.get("confirm_password", ""))

        if not code:
            return err(_("error::code is required"))
        if not email and not phone:
            return err(_("error::email or phone is required"))

        min_len = settings.min_password_length or 6
        if not password or len(password) < min_len:
            return err(
                _("error::password must be at least %(n)s characters")
                % {"n": min_len}
            )
        if settings.require_confirm_password:
            if not password_confirm:
                return err(_("error::password confirmation is required"))
            if password != password_confirm:
                return err(_("error::passwords do not match"))

        q = Q()
        if email:
            q |= Q(email=email)
        if phone:
            q |= Q(phone_number=phone)
        user = User.objects.filter(q).first()
        if not user:
            return err(_("error::invalid code or contact"))

        is_valid, instance = AuthCode.validate(
            user=user, code=code, purpose=AuthCode.PURPOSE_PASSWORD_RESET
        )
        if not is_valid:
            return err(_("error::code is incorrect or expired"))

        instance.consume()
        user.set_password(password)
        if settings.activate_after_successful_otp:
            user.is_active = True
        if email and hasattr(user, "email_verified"):
            user.email_verified = True
        if phone and hasattr(user, "phone_number_verified"):
            user.phone_number_verified = True
        user.save()
        AuthCode.objects.filter(user=user).delete()

        if not user.is_active:
            return err(
                _("error::account is inactive. contact admin"),
                status.HTTP_403_FORBIDDEN,
            )

        tokens = get_tokens_for_user(user)
        LoginLog.record(
            user=user,
            request=request,
            event=LoginLog.EVENT_PASSWORD_RESET,
            method=LoginLog.METHOD_PASSWORD,
            success=True,
            identifier=(
                (data.get("email") or data.get("phone_number") or data.get("username") or "")[:255]
                if isinstance(data, dict)
                else ""
            ),
        )
        return ok(
            _("success::password reset and logged in"),
            {**tokens, "next_step": "done"},
        )


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------
