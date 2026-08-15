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
