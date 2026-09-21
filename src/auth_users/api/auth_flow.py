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


def _identifier_from_data(data):
    for k in ("email", "phone_number", "username"):
        v = (data.get(k) or "").strip() if isinstance(data.get(k), str) else data.get(k)
        if v:
            return str(v)[:255]
    return ""


def _log_success(user, request, data, method):
    LoginLog.record(
        user=user,
        request=request,
        event=LoginLog.EVENT_SUCCESS,
        method=method,
        success=True,
        identifier=_identifier_from_data(data),
    )


def _log_failed(request, data, reason, user=None):
    LoginLog.record(
        user=user,
        request=request,
        event=LoginLog.EVENT_FAILED,
        method=LoginLog.METHOD_OTHER,
        success=False,
        identifier=_identifier_from_data(data),
        failure_reason=reason,
    )



# ---------------------------------------------------------------------------
# Public endpoint: current login settings
# ---------------------------------------------------------------------------
class StartAuthAPIView(APIView):
    """
    Unified entry point.

    Body:
        username, email, phone_number  (any allowed combination)
        invite  (optional / required depending on LoginSettings)

    When allow_auto_signup=False (or require_invite_for_signup=True):
        a valid invite token is mandatory to create a new account.
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

        data = {k: (v or "").strip() if isinstance(v, str) else v for k, v in request.data.items()}
        invite_token = (data.get("invite") or data.get("invite_token") or "").strip()

        validation_err = validate_required_identifiers(data, settings)
        if validation_err:
            return err(validation_err)

        user, lookup_err = resolve_user_from_identifiers(data, settings)

        # ---------- User does not exist → maybe create ----------
        if user is None:
            allowed, invite, create_err = can_create_user(settings, invite_token)
            if not allowed:
                return err(create_err or _("error::signup is closed"), status.HTTP_403_FORBIDDEN)

            serializer = CreateUserSerializer(data=request.data)
            if not serializer.is_valid():
                return err(
                    _("error::user not created"),
                    extra={"errors": serializer.errors},
                )
            user = serializer.save()
            # Ensure brand-new users do not appear to "already have a password"
            # unless the client explicitly sent one in this request.
            client_password = (request.data.get("password") or "").strip()
            if not client_password:
                user.set_unusable_password()
                user.save(update_fields=["password"])
            if not settings.auto_activate_on_signup:
                user.is_active = False
                user.save(update_fields=["is_active"])

            # Record invite usage
            if invite is not None:
                try:
                    invite.consume(user, request=request)
                except ValidationError as e:
                    # Extremely rare race condition – delete the just-created user
                    user.delete()
                    return err(str(e), status.HTTP_403_FORBIDDEN)

            created = True
        else:
            created = False
            # Existing user logging in – invite is irrelevant

        # ---------- Decide next step ----------
        # Priority:
        #   1) OTP first (if required) so the code is verified before password
        #   2) set_password for brand-new users that must set a password
        #   3) password (2FA) for existing users that already have one
        channel, contact = extract_contact(data, settings)
        if settings.require_otp and not channel:
            return err(_("error::email or phone required to send code"))

        has_password = user.has_usable_password()
        user_needs_to_set_password = (not has_password) and (
            (created and settings.require_password_on_signup)
            or (not has_password and settings.require_password and created)
        )

        if settings.require_otp:
            next_step = "otp"
        elif user_needs_to_set_password:
            next_step = "set_password"
        elif has_password and settings.needs_password(user):
            next_step = "password"
        else:
            if not user.is_active and not settings.activate_after_successful_otp:
                return err(
                    _("error::account is inactive. contact admin"),
                    status.HTTP_403_FORBIDDEN,
                )
            tokens = get_tokens_for_user(user)
            _log_success(user, request, data, LoginLog.METHOD_OTHER)
            return ok(_("success::logged in"), tokens)

        if settings.require_otp and channel:
            send_otp(
                user=user,
                contact=contact,
                channel=channel,
                purpose=AuthCode.PURPOSE_SIGNUP if created else AuthCode.PURPOSE_LOGIN,
            )

        response_data = {
            "next_step": next_step,
            "created": created,
            "requires_password": user_needs_to_set_password or settings.needs_password(user),
            "requires_otp": settings.require_otp,
            "channel": channel,
            "invite_used": bool(created and invite_token),
        }
        return ok(
            _("success::code sent") if settings.require_otp else _("success::continue"),
            response_data,
            status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Step 2 – Verify OTP
# ---------------------------------------------------------------------------
class ValidateOTPAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        settings = LoginSettings.get_solo()
        if not settings.allow_login:
            return err(
                settings.custom_login_closed_message
                or _("error::login is temporarily closed"),
                status.HTTP_403_FORBIDDEN,
            )

        data = {k: (v or "").strip() if isinstance(v, str) else v for k, v in request.data.items()}
        code = data.get("code", "")

        if not settings.require_otp:
            return err(_("error::otp is not required by current settings"))

        validation_err = validate_required_identifiers(data, settings)
        if validation_err:
            return err(validation_err)

        user, lookup_err = resolve_user_from_identifiers(data, settings)
        if user is None:
            return err(lookup_err or _("error::user not found"), status.HTTP_404_NOT_FOUND)

        is_valid, instance = AuthCode.validate(
            user=user, code=code, purpose=AuthCode.PURPOSE_LOGIN
        )
        if not is_valid:
            is_valid, instance = AuthCode.validate(
                user=user, code=code, purpose=AuthCode.PURPOSE_SIGNUP
            )

        if not is_valid:
            _log_failed(request, data, "otp incorrect or expired", user=user)
            return err(_("error::code is incorrect or expired"))

        if settings.activate_after_successful_otp:
            user.is_active = True
        if data.get("email") and hasattr(user, "email_verified"):
            user.email_verified = True
        if data.get("phone_number") and hasattr(user, "phone_number_verified"):
            user.phone_number_verified = True
        user.save()

        instance.consume()

        # After a valid OTP, decide what comes next.
        # If the user has NO usable password → they must SET one (not "enter" one).
        has_password = user.has_usable_password()
        needs_set_password = (not has_password) and (
            settings.require_password_on_signup or settings.require_password
        )
        needs_pwd = has_password and settings.needs_password(user)

        if needs_set_password:
            return ok(
                _("success::code valid"),
                {
                    "is_valid": True,
                    "twofactor": False,
                    "next_step": "set_password",
                    "must_set_password": True,
                },
            )

        if needs_pwd:
            return ok(
                _("success::code valid"),
                {
                    "is_valid": True,
                    "twofactor": True,
                    "next_step": "password",
                },
            )

        if not user.is_active:
            return err(
                _("error::account is inactive. contact admin"),
                status.HTTP_403_FORBIDDEN,
            )
        tokens = get_tokens_for_user(user)
        _log_success(user, request, data, LoginLog.METHOD_OTP)
        return ok(
            _("success::user is valid"),
            {
                "is_valid": True,
                "twofactor": False,
                "next_step": "done",
                **tokens,
            },
        )


# ---------------------------------------------------------------------------
# Step 3 – Final login with password
# ---------------------------------------------------------------------------
class FinalAuthAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        settings = LoginSettings.get_solo()
        if not settings.allow_login:
            return err(
                settings.custom_login_closed_message
                or _("error::login is temporarily closed"),
                status.HTTP_403_FORBIDDEN,
            )

        data = {k: (v or "").strip() if isinstance(v, str) else v for k, v in request.data.items()}
        password = data.get("password", "")
        code = data.get("code", "")

        validation_err = validate_required_identifiers(data, settings)
        if validation_err:
            return err(validation_err)

        user, lookup_err = resolve_user_from_identifiers(data, settings)
        if user is None:
            return err(lookup_err or _("error::user not found"), status.HTTP_404_NOT_FOUND)

        if settings.require_otp:
            if not code:
                return err(_("error::code is required"))
            is_valid, instance = AuthCode.validate(
                user=user, code=code, purpose=AuthCode.PURPOSE_LOGIN
            )
            if not is_valid:
                is_valid, instance = AuthCode.validate(
                    user=user, code=code, purpose=AuthCode.PURPOSE_SIGNUP
                )
            if not is_valid:
                return err(_("error::code is incorrect or expired"))

        if settings.needs_password(user):
            if not password:
                return err(_("error::password is required"))
            if not user.has_usable_password() or not user.check_password(password):
                _log_failed(request, data, "password incorrect", user=user)
                return err(_("error::password is incorrect"))

        if settings.require_otp and code:
            AuthCode.objects.filter(user=user).delete()

        if settings.activate_after_successful_otp or settings.auto_activate_on_signup:
            user.is_active = True
        if data.get("email") and hasattr(user, "email_verified"):
            user.email_verified = True
        if data.get("phone_number") and hasattr(user, "phone_number_verified"):
            user.phone_number_verified = True
        user.save()

        if not user.is_active:
            return err(
                _("error::account is inactive. contact admin"),
                status.HTTP_403_FORBIDDEN,
            )

        tokens = get_tokens_for_user(user)
        method = LoginLog.METHOD_OTP_PASSWORD if settings.require_otp else LoginLog.METHOD_PASSWORD
        _log_success(user, request, data, method)
        return ok(_("success::user logged in"), tokens)


# ---------------------------------------------------------------------------
# Set password
# ---------------------------------------------------------------------------
class SetPasswordAPIView(APIView):
    """
    Set password for a newly created user.

    OTP handling:
    - If require_otp=True and a code is still present → validate it (and consume).
    - If require_otp=True but code was already consumed in /login/validate/
      (normal flow: otp → set_password) → do NOT require the code again.
    - If require_otp=False → just set the password.
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

        data = {k: (v or "").strip() if isinstance(v, str) else v for k, v in request.data.items()}
        password = data.get("password", "")
        password_confirm = data.get("password_confirm", data.get("confirm_password", ""))
        code = data.get("code", "")

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

        user, lookup_err = resolve_user_from_identifiers(data, settings)
        if user is None:
            return err(lookup_err or _("error::user not found"), status.HTTP_404_NOT_FOUND)

        # Optional OTP check: only enforce when a code is supplied OR
        # when an AuthCode still exists for this user (OTP not yet verified).
        if settings.require_otp:
            has_pending_code = AuthCode.objects.filter(user=user).exists()
            if has_pending_code:
                if not code:
                    return err(_("error::code is required"))
                is_valid, instance = AuthCode.validate(
                    user=user, code=code, purpose=AuthCode.PURPOSE_SIGNUP
                )
                if not is_valid:
                    is_valid, instance = AuthCode.validate(
                        user=user, code=code, purpose=AuthCode.PURPOSE_LOGIN
                    )
                if not is_valid:
                    return err(_("error::code is incorrect or expired"))
                if instance:
                    instance.consume()

        user.set_password(password)
        if settings.activate_after_successful_otp or settings.auto_activate_on_signup:
            user.is_active = True
        if data.get("email") and hasattr(user, "email_verified"):
            user.email_verified = True
        if data.get("phone_number") and hasattr(user, "phone_number_verified"):
            user.phone_number_verified = True
        user.save()

        # Clean up any leftover codes
        AuthCode.objects.filter(user=user).delete()

        if not user.is_active:
            return err(
                _("error::account is inactive. contact admin"),
                status.HTTP_403_FORBIDDEN,
            )

        tokens = get_tokens_for_user(user)
        _log_success(user, request, data, LoginLog.METHOD_PASSWORD)
        return ok(_("success::password set and logged in"), {**tokens, "next_step": "done"})


# ---------------------------------------------------------------------------
# Username recovery
# ---------------------------------------------------------------------------
