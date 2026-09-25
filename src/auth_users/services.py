"""
Business logic helpers for the customizable auth system.
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings as django_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from django.utils.translation import gettext as _
import hashlib
import uuid

from .models import Device, LoginSettings, AuthCode, InviteLink, UserSession

User = get_user_model()


class SessionLimitExceeded(AuthenticationFailed):
    """Raised when the configured login policy rejects a new session."""


def _request_metadata(request):
    if request is None:
        return {}
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = xff.split(",", 1)[0].strip() if xff else request.META.get("REMOTE_ADDR")
    return {
        "last_ip": ip or None,
        "user_agent": (request.META.get("HTTP_USER_AGENT", "") or "")[:500],
    }


def _device_id(value):
    if not value:
        return uuid.uuid4()
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return uuid.uuid4()


def issue_tokens_for_user(user, *, request=None, device_id=None, device=None):
    """Create a revocable session and issue JWTs carrying its session identity.

    The user row is locked while the active-session policy is enforced. The
    refresh token is hashed into the session row; no token credential is
    persisted in plaintext.
    """
    if not user.is_active:
        raise AuthenticationFailed(_("error::user is not active"))

    metadata = _request_metadata(request)
    with transaction.atomic():
        locked_user = User.objects.select_for_update().get(pk=user.pk)
        if not locked_user.is_active:
            raise AuthenticationFailed(_("error::user is not active"))

        policy = LoginSettings.get_solo()
        now = timezone.now()
        active = UserSession.objects.filter(
            user=locked_user,
            revoked_at__isnull=True,
            expires_at__gt=now,
        ).order_by("created_at")
        active_count = active.count()
        if active_count >= policy.max_active_sessions:
            if policy.session_eviction_policy == LoginSettings.SessionEvictionPolicy.REJECT_NEW:
                raise SessionLimitExceeded(_("error::session limit reached"))
            revoke_count = active_count - policy.max_active_sessions + 1
            for old in active[:revoke_count]:
                old.revoke(at=now)
                old.save(update_fields=["revoked_at"])

        refresh = RefreshToken.for_user(locked_user)
        session_id = str(refresh["jti"])
        refresh["sid"] = session_id
        access = refresh.access_token
        device_obj = device
        if device_obj is None:
            requested_device_id = _device_id(device_id)
            device_obj, _ = Device.objects.get_or_create(
                user=locked_user,
                public_id=requested_device_id,
                defaults={
                    "platform": str((request.data.get("platform") if request else "") or "")[:64],
                    "client": str((request.data.get("client") if request else "") or "")[:120],
                    **metadata,
                },
            )
        else:
            device_obj.user = locked_user
        if device_obj.revoked_at is not None:
            raise AuthenticationFailed(_("error::device is revoked"))
        Device.objects.filter(pk=device_obj.pk).update(
            last_seen_at=now,
            last_ip=metadata.get("last_ip"),
            user_agent=metadata.get("user_agent", ""),
        )

        refresh_text = str(refresh)
        session = UserSession.objects.create(
            session_id=session_id,
            user=locked_user,
            device=device_obj,
            credential_hash=hashlib.sha256(refresh_text.encode("utf-8")).hexdigest(),
            expires_at=now + jwt_settings.REFRESH_TOKEN_LIFETIME,
            last_ip=metadata.get("last_ip"),
            user_agent=metadata.get("user_agent", ""),
        )

    return {"refresh": refresh_text, "access": str(access), "session_id": session.session_id}


def get_tokens_for_user(user, *, request=None, device_id=None):
    """Compatibility entry point used by existing auth flows."""
    return issue_tokens_for_user(user, request=request, device_id=device_id)


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
                "OTP delivery pending for contact=%s purpose=%s",
                contact,
                purpose,
            )
    else:
        import logging
        logging.getLogger("auth_users").info(
            "SMS delivery not implemented. contact=%s purpose=%s",
            contact or (user.username if user else ""),
            purpose,
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
