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
from .models import LoginSettings, AuthCode, InviteLink, InviteUsage
from .services import (
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
                    "otp_length": s.otp_length,
                    "otp_expire_minutes": s.otp_expire_minutes,
                }
            },
        )


# ---------------------------------------------------------------------------
# Invite validation (public – frontend checks before showing form)
# GET /api/invite/validate/?token=xxx
# ---------------------------------------------------------------------------
class InviteValidateAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        token = (request.query_params.get("token") or "").strip()
        invite, error = resolve_invite(token)
        if error:
            return err(error, status.HTTP_400_BAD_REQUEST)
        return ok(
            _("success::invite is valid"),
            {
                "valid": True,
                "label": invite.label,
                "remaining_uses": invite.remaining_uses(),
                "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
            },
        )


# ---------------------------------------------------------------------------
# Admin: create / list invite links
# ---------------------------------------------------------------------------
class InviteCreateAPIView(APIView):
    """
    POST /api/invite/create/
    Body (all optional except nothing required):
      {
        "label": "Beta batch 1",
        "max_uses": 1,          // 1 = one-time, null/omit = unlimited
        "expires_at": "2026-12-31T23:59:59Z",  // optional ISO datetime
        "base_url": "https://echonode.website" // optional, for full URL in response
      }
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        label = (request.data.get("label") or "").strip()
        max_uses = request.data.get("max_uses", None)
        expires_at_raw = request.data.get("expires_at")
        base_url = (request.data.get("base_url") or "").strip()

        if max_uses is not None:
            try:
                max_uses = int(max_uses)
                if max_uses < 1:
                    return err(_("error::max_uses must be >= 1 or null"))
            except (TypeError, ValueError):
                return err(_("error::max_uses must be an integer or null"))

        expires_at = None
        if expires_at_raw:
            from django.utils.dateparse import parse_datetime
            expires_at = parse_datetime(str(expires_at_raw))
            if expires_at is None:
                return err(_("error::invalid expires_at format (use ISO 8601)"))
            if timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at)

        invite = InviteLink.objects.create(
            label=label,
            max_uses=max_uses,
            expires_at=expires_at,
            created_by=request.user if request.user.is_authenticated else None,
        )

        return ok(
            _("success::invite created"),
            {
                "token": invite.token,
                "url": invite.get_invite_url(base_url),
                "label": invite.label,
                "max_uses": invite.max_uses,
                "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
                "is_active": invite.is_active,
            },
            status.HTTP_201_CREATED,
        )


class InviteListAPIView(APIView):
    """GET /api/invite/list/ – admin only"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = InviteLink.objects.all().prefetch_related("usages__user")
        results = []
        for inv in qs:
            results.append({
                "id": inv.id,
                "token": inv.token,
                "label": inv.label,
                "max_uses": inv.max_uses,
                "uses_count": inv.uses_count,
                "remaining_uses": inv.remaining_uses(),
                "is_active": inv.is_active,
                "is_valid": inv.is_valid(),
                "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
                "created_at": inv.created_at.isoformat(),
                "created_by": inv.created_by.username if inv.created_by else None,
                "url": inv.get_invite_url(request.build_absolute_uri("/").rstrip("/").replace("/auth", "")),
                "users": [
                    {
                        "username": u.user.username,
                        "email": getattr(u.user, "email", None),
                        "used_at": u.used_at.isoformat(),
                        "ip_address": u.ip_address,
                    }
                    for u in inv.usages.all()
                ],
            })
        return ok(_("success::invite list"), {"invites": results})


class InviteDeactivateAPIView(APIView):
    """POST /api/invite/deactivate/  body: {"token": "..."}"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        token = (request.data.get("token") or "").strip()
        if not token:
            return err(_("error::token is required"))
        try:
            invite = InviteLink.objects.get(token=token)
        except InviteLink.DoesNotExist:
            return err(_("error::invite not found"), status.HTTP_404_NOT_FOUND)
        invite.is_active = False
        invite.save(update_fields=["is_active", "updated_at"])
        return ok(_("success::invite deactivated"))


# ---------------------------------------------------------------------------
# Step 1 – Send OTP / start auth flow  (with invite support)
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
        data = {k: (v or "").strip() if isinstance(v, str) else v for k, v in request.data.items()}
        password = data.get("password", "")
        code = data.get("code", "")

        if not password or len(password) < 6:
            return err(_("error::password must be at least 6 characters"))

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
        return ok(_("success::password set and logged in"), {**tokens, "next_step": "done"})


# ---------------------------------------------------------------------------
# Username recovery
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
# Legacy aliases
# ---------------------------------------------------------------------------
class LoginAPIView(StartAuthAPIView):
    pass


class SignupOrLoginAPIView(StartAuthAPIView):
    pass


class AuthAPIView(FinalAuthAPIView):
    pass


class ValidateAPIView(ValidateOTPAPIView):
    pass
