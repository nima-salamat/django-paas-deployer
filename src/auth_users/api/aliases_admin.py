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
from .auth_flow import StartAuthAPIView, FinalAuthAPIView, ValidateOTPAPIView

class ValidateToken(APIView):
    permission_classes = [IsAuthenticated]

    def _payload(self, request):
        u = request.user
        return {
            "status": "valid access token",
            "success": True,
            "user": {
                "id": u.id,
                "username": getattr(u, "username", None),
                "email": getattr(u, "email", None),
                "is_staff": bool(getattr(u, "is_staff", False)),
                "is_superuser": bool(getattr(u, "is_superuser", False)),
            },
        }

    def post(self, request):
        return Response(self._payload(request), status=status.HTTP_200_OK)

    def get(self, request):
        return Response(self._payload(request), status=status.HTTP_200_OK)


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


# ---------------------------------------------------------------------------
# Admin: Auth codes list / delete
# ---------------------------------------------------------------------------
class AdminAuthCodeListAPIView(APIView):
    """GET /auth/api/admin/auth-codes/ – list OTP codes (staff with permission / admin)."""
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        from django.utils import timezone as tz
        qs = AuthCode.objects.select_related("user").order_by("-created_at")
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(user__username__icontains=search)
                | Q(user__email__icontains=search)
                | Q(contact__icontains=search)
                | Q(code__icontains=search)
            )
        purpose = (request.query_params.get("purpose") or "").strip()
        if purpose:
            qs = qs.filter(purpose=purpose)
        # Pagination simple
        try:
            page = max(int(request.query_params.get("page", 1)), 1)
        except ValueError:
            page = 1
        page_size = 25
        total = qs.count()
        start = (page - 1) * page_size
        items = []
        for c in qs[start : start + page_size]:
            items.append({
                "id": c.id,
                "user_id": c.user_id,
                "username": getattr(c.user, "username", None) if c.user_id else None,
                "contact": getattr(c, "contact", None) or "",
                "purpose": c.purpose,
                "code": c.code,
                "attempts": getattr(c, "attempts", 0),
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if getattr(c, "updated_at", None) else None,
                "is_expired": c.is_expired(),
                "is_locked": c.is_locked(),
            })
        return ok(
            _("success::auth codes"),
            {"results": items, "count": total, "page": page, "page_size": page_size},
        )


class AdminAuthCodeDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def delete(self, request, pk):
        deleted, _ = AuthCode.objects.filter(pk=pk).delete()
        if not deleted:
            return err(_("error::not found"), status.HTTP_404_NOT_FOUND)
        return ok(_("success::deleted"))


class AdminAuthCodePurgeAPIView(APIView):
    """DELETE expired/used codes."""
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        # OTP expiry is computed from updated_at + LoginSettings.otp_expire_minutes
        from django.utils import timezone as tz
        from datetime import timedelta
        from ..models import LoginSettings
        minutes = LoginSettings.get_solo().otp_expire_minutes or 5
        cutoff = tz.now() - timedelta(minutes=minutes)
        qs = AuthCode.objects.filter(updated_at__lt=cutoff)
        n, _ = qs.delete()
        return ok(_("success::purged"), {"deleted": n})
