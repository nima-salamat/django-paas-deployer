"""
Business logic helpers for the customizable auth system.
"""
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from django.utils.translation import gettext as _

from .models import LoginSettings, AuthCode, InviteLink

User = get_user_model()


def get_tokens_for_user(user):
    if not user.is_active:
        raise AuthenticationFailed(_("error::user is not active"))
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


def resolve_user_from_identifiers(data, settings: LoginSettings):
    """
    Build a lookup from the allowed identifiers present in `data`.
    Returns (user, error_message).
    """
    lookup = {}
    if settings.allow_username and data.get("username"):
        lookup["username"] = data["username"].strip()
    if settings.allow_email and data.get("email"):
        lookup["email"] = data["email"].strip().lower()
    if settings.allow_phone and data.get("phone_number"):
        lookup["phone_number"] = data["phone_number"].strip()

    if not lookup:
        return None, _("error::at least one allowed identifier is required")

    try:
        user = User.objects.get(**lookup)
        return user, None
    except User.DoesNotExist:
        pass
    except User.MultipleObjectsReturned:
        return None, _("error::multiple users match these identifiers")

    # Fallback: try each identifier independently
    q = Q()
    if "username" in lookup:
        q |= Q(username=lookup["username"])
    if "email" in lookup:
        q |= Q(email=lookup["email"])
    if "phone_number" in lookup:
        q |= Q(phone_number=lookup["phone_number"])

    users = User.objects.filter(q)
    if users.count() == 1:
        return users.first(), None
    if users.count() > 1:
        return None, _("error::multiple users match these identifiers")
    return None, _("error::user not found")


def extract_contact(data, settings: LoginSettings):
    """Return the best contact channel for sending OTP."""
    if settings.allow_email and data.get("email"):
        return "email", data["email"].strip().lower()
    if settings.allow_phone and data.get("phone_number"):
        return "phone", data["phone_number"].strip()
    return None, None


def send_otp(user=None, contact="", channel="email", purpose=AuthCode.PURPOSE_LOGIN):
    """
    Create/refresh code and dispatch it.
    Replace the SMS stub with a real implementation when ready.
    """
    from core.tasks.email import send_code_via_email

    instance = AuthCode.create_or_refresh(
        user=user,
        contact=contact if not user else "",
        purpose=purpose,
    )
    code = instance.code

    if channel == "email":
        if user:
            send_code_via_email.delay(user.id)
        else:
            import logging
            logging.getLogger("auth_users").info(
                f"OTP for contact={contact} purpose={purpose} code={code}"
            )
    else:
        import logging
        logging.getLogger("auth_users").info(
            f"SMS not implemented. contact={contact or (user.username if user else '')} code={code}"
        )
    return code


def validate_required_identifiers(data, settings: LoginSettings):
    """
    Check that at least one allowed identifier is present.
    Returns error message or None.
    """
    has_any = False
    if settings.allow_username and data.get("username"):
        has_any = True
    if settings.allow_email and data.get("email"):
        has_any = True
    if settings.allow_phone and data.get("phone_number"):
        has_any = True
    if not has_any:
        allowed = settings.get_allowed_identifiers()
        return _("error::provide one of: %(fields)s") % {"fields": ", ".join(allowed)}
    return None


def resolve_invite(token: str):
    """
    Validate an invite token.
    Returns (invite_or_None, error_message_or_None).
    """
    if not token:
        return None, _("error::invite token is required")
    invite = InviteLink.get_valid(token)
    if invite is None:
        # Distinguish reasons for better UX
        try:
            raw = InviteLink.objects.get(token=token)
        except InviteLink.DoesNotExist:
            return None, _("error::invalid invite link")
        if not raw.is_active:
            return None, _("error::invite link has been disabled")
        if raw.is_expired():
            return None, _("error::invite link has expired")
        if raw.is_exhausted():
            return None, _("error::invite link has reached its usage limit")
        return None, _("error::invalid invite link")
    return invite, None


def can_create_user(settings: LoginSettings, invite_token: str = ""):
    """
    Decide whether a new user may be created right now.
    Returns (allowed: bool, invite_or_None, error_message_or_None).
    """
    if settings.allow_auto_signup and not settings.require_invite_for_signup:
        # Open signup – invite is optional
        if invite_token:
            invite, err = resolve_invite(invite_token)
            if err:
                # Invalid invite should not block open signup
                return True, None, None
            return True, invite, None
        return True, None, None

    # Signup is restricted – invite is mandatory
    if not invite_token:
        return False, None, _("error::signup is closed. an invite link is required")

    invite, err = resolve_invite(invite_token)
    if err:
        return False, None, err
    return True, invite, None
