import logging
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _
from django.db.models import Q

from users.serializers import CreateUserSerializer
from .models import LoginSettings, AuthCode
from .services import (
    get_tokens_for_user,
    resolve_user_from_identifiers,
    extract_contact,
    send_otp,
    validate_required_identifiers,
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
# Public endpoint: current login settings (frontend uses this to render UI)
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
                    "allow_username_recovery": s.allow_username_recovery,
                    "recovery_via_email": s.recovery_via_email,
                    "recovery_via_phone": s.recovery_via_phone,
                    "otp_length": s.otp_length,
                    "otp_expire_minutes": s.otp_expire_minutes,
                }
            },
        )


# ---------------------------------------------------------------------------
# Step 1 – Send OTP / start auth flow
# Endpoint: POST /api/authentication/
# ---------------------------------------------------------------------------
class StartAuthAPIView(APIView):
    """
    Unified entry point.

    Body can contain any combination of:
        username, email, phone_number

    Behaviour is driven by LoginSettings:
    - If user exists -> send OTP (if require_otp) and return next_step
    - If user does not exist and allow_auto_signup -> create user,
      optionally ask for password, send OTP
    - If user does not exist and not allow_auto_signup -> 404
    """

    permission_classes = [AllowAny]

    def post(self, request):
        settings = LoginSettings.get_solo()
        data = {k: (v or "").strip() for k, v in request.data.items()}

        validation_err = validate_required_identifiers(data, settings)
        if validation_err:
            return err(validation_err)

        user, lookup_err = resolve_user_from_identifiers(data, settings)

        # ---------- User does not exist ----------
        if user is None:
            if not settings.allow_auto_signup:
                return err(
                    lookup_err or _("error::user not found"),
                    status.HTTP_404_NOT_FOUND,
                )

            serializer = CreateUserSerializer(data=request.data)
            if not serializer.is_valid():
                return err(
                    _("error::user not created"),
                    extra={"errors": serializer.errors},
                )
            user = serializer.save()
            if not settings.auto_activate_on_signup:
                user.is_active = False
                user.save(update_fields=["is_active"])

            created = True
        else:
            created = False

        # ---------- Decide next step ----------
        channel, contact = extract_contact(data, settings)
        if settings.require_otp and not channel:
            return err(_("error::email or phone required to send code"))

        next_step = "done"
        needs_password_now = False

        if created and settings.require_password_on_signup:
            needs_password_now = True
            next_step = "set_password"
        elif settings.require_otp:
            next_step = "otp"
        elif settings.needs_password(user):
            next_step = "password"
        else:
            if not user.is_active and not settings.activate_after_successful_otp:
                return err(
                    _("error::account is inactive. contact admin"),
                    status.HTTP_403_FORBIDDEN,
                )
            tokens = get_tokens_for_user(user)
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
            "requires_password": needs_password_now or settings.needs_password(user),
            "requires_otp": settings.require_otp,
            "channel": channel,
        }
        return ok(
            _("success::code sent") if settings.require_otp else _("success::continue"),
            response_data,
            status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Step 2 – Verify OTP
# Endpoint: POST /api/login/validate/
# ---------------------------------------------------------------------------
class ValidateOTPAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        settings = LoginSettings.get_solo()
        data = {k: (v or "").strip() for k, v in request.data.items()}
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
            return err(_("error::code is incorrect or expired"))

        if settings.activate_after_successful_otp:
            user.is_active = True
        if data.get("email") and hasattr(user, "email_verified"):
            user.email_verified = True
        if data.get("phone_number") and hasattr(user, "phone_number_verified"):
            user.phone_number_verified = True
        user.save()

        instance.consume()

        needs_pwd = settings.needs_password(user)
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
# Step 3 – Final login with password (and optional OTP already verified)
# Endpoint: POST /api/login/token/
# ---------------------------------------------------------------------------
class FinalAuthAPIView(APIView):
    """
    Used when password is required (with or without prior OTP).
    Also used for pure password login when require_otp=False.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        settings = LoginSettings.get_solo()
        data = {k: (v or "").strip() for k, v in request.data.items()}
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
        return ok(_("success::user logged in"), tokens)


# ---------------------------------------------------------------------------
# Set password (for new users when require_password_on_signup=True)
# Endpoint: POST /api/set-password/
# ---------------------------------------------------------------------------
class SetPasswordAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        settings = LoginSettings.get_solo()
        data = {k: (v or "").strip() for k, v in request.data.items()}
        password = data.get("password", "")
        code = data.get("code", "")

        if not password or len(password) < 6:
            return err(_("error::password must be at least 6 characters"))

        user, lookup_err = resolve_user_from_identifiers(data, settings)
        if user is None:
            return err(lookup_err or _("error::user not found"), status.HTTP_404_NOT_FOUND)

        if settings.require_otp:
            if not code:
                return err(_("error::code is required"))
            is_valid, _ = AuthCode.validate(
                user=user, code=code, purpose=AuthCode.PURPOSE_SIGNUP
            )
            if not is_valid:
                is_valid, _ = AuthCode.validate(
                    user=user, code=code, purpose=AuthCode.PURPOSE_LOGIN
                )
            if not is_valid:
                return err(_("error::code is incorrect or expired"))

        user.set_password(password)
        if settings.activate_after_successful_otp:
            user.is_active = True
        user.save()

        if settings.require_otp and not code:
            return ok(
                _("success::password set"),
                {"next_step": "otp"},
            )

        AuthCode.objects.filter(user=user).delete()

        if not user.is_active:
            return err(
                _("error::account is inactive. contact admin"),
                status.HTTP_403_FORBIDDEN,
            )

        tokens = get_tokens_for_user(user)
        return ok(_("success::password set and logged in"), {**tokens, "next_step": "done"})


# ---------------------------------------------------------------------------
# Username recovery – Step 1: request OTP
# Endpoint: POST /api/recovery/request/
# ---------------------------------------------------------------------------
class RecoveryRequestAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        settings = LoginSettings.get_solo()
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
            # Do not leak existence
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


# ---------------------------------------------------------------------------
# Username recovery – Step 2: verify OTP and return username
# Endpoint: POST /api/recovery/confirm/
# ---------------------------------------------------------------------------
class RecoveryConfirmAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        settings = LoginSettings.get_solo()
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
# Token validation
# ---------------------------------------------------------------------------
class ValidateToken(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response({"status": "valid access token"}, status=status.HTTP_200_OK)

    def get(self, request):
        return Response({"status": "valid access token"}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Legacy-compatible thin wrappers
# ---------------------------------------------------------------------------
class LoginAPIView(StartAuthAPIView):
    pass


class SignupOrLoginAPIView(StartAuthAPIView):
    pass


class AuthAPIView(FinalAuthAPIView):
    pass


class ValidateAPIView(ValidateOTPAPIView):
    pass
