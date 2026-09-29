from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SessionJWTAuthentication
from .models import Device, LoginSettings, UserSession
from .session_auth import (
    ensure_session_can_revoke_others,
    session_management_min_age,
    invalidate_all_sessions,
    invalidate_device,
    invalidate_session,
)


class SessionAPIBase(APIView):
    authentication_classes = [SessionJWTAuthentication]
    permission_classes = [IsAuthenticated]


def _current_session_id(request):
    return getattr(request.auth, "get", lambda *_: None)("sid") if request.auth else None


def _require_current_session(request):
    session_id = _current_session_id(request)
    if not session_id:
        return None
    return session_id


def _session_payload(session, current_id=None):
    return {
        "id": session.session_id,
        "device_id": str(session.device.public_id),
        "device": {
            "name": session.device.name,
            "platform": session.device.platform,
            "client": session.device.client,
        },
        "created_at": session.created_at,
        "last_seen_at": session.last_seen_at,
        "expires_at": session.expires_at,
        "current": session.session_id == current_id,
    }


class SessionListAPIView(SessionAPIBase):
    def get(self, request):
        current_id = getattr(request.auth, "get", lambda *_: None)("sid") if request.auth else None
        now = timezone.now()
        sessions = list(
            UserSession.objects.filter(
                user=request.user,
                revoked_at__isnull=True,
                expires_at__gt=now,
            )
            .select_related("device")
            .order_by("-last_seen_at")
        )
        policy = LoginSettings.get_solo()
        current_session = next(
            (session for session in sessions if session.session_id == current_id),
            None,
        )
        min_management_age = session_management_min_age()
        current_age_seconds = (
            max(0, int((now - current_session.created_at).total_seconds()))
            if current_session is not None
            else 0
        )
        can_revoke_others = current_session is not None and (
            current_age_seconds >= int(min_management_age.total_seconds())
        )
        return Response(
            {
                "results": [_session_payload(s, current_id) for s in sessions],
                "active_count": len(sessions),
                "max_active_sessions": policy.max_active_sessions,
                "session_management": {
                    "minimum_age_seconds": int(min_management_age.total_seconds()),
                    "current_session_age_seconds": current_age_seconds,
                    "can_revoke_others": can_revoke_others,
                },
            }
        )


class SessionRevokeAPIView(SessionAPIBase):
    def delete(self, request, session_id):
        session = UserSession.objects.filter(
            user=request.user,
            session_id=session_id,
        ).first()
        if session is None:
            return Response({"detail": "Session not found."}, status=404)

        current_id = _current_session_id(request)
        if current_id and str(session.session_id) != str(current_id):
            ensure_session_can_revoke_others(
                str(current_id),
                user_id=request.user.id,
            )
        elif not current_id:
            return Response(
                {
                    "code": "session_context_required",
                    "detail": "A session-bound authentication token is required to revoke another session.",
                },
                status=403,
            )

        invalidate_session(session.session_id)
        return Response(status=204)


class SessionLogoutAllAPIView(SessionAPIBase):
    def post(self, request):
        current_id = _require_current_session(request)
        if not current_id:
            return Response(
                {
                    "code": "session_context_required",
                    "detail": "A session-bound authentication token is required for session management.",
                },
                status=403,
            )

        other_exists = UserSession.objects.filter(
            user=request.user,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).exclude(session_id=current_id).exists()

        if other_exists:
            ensure_session_can_revoke_others(
                str(current_id),
                user_id=request.user.id,
            )

        count = invalidate_all_sessions(request.user.id)
        return Response({"revoked": count})


class DeviceListAPIView(SessionAPIBase):
    def get(self, request):
        now = timezone.now()
        devices = (
            Device.objects.filter(user=request.user)
            .annotate(
                active_session_count=Count(
                    "sessions",
                    filter=Q(
                        sessions__revoked_at__isnull=True,
                        sessions__expires_at__gt=now,
                    ),
                )
            )
            .order_by("-last_seen_at")
        )
        return Response(
            {
                "results": [
                    {
                        "id": str(device.public_id),
                        "name": device.name,
                        "platform": device.platform,
                        "client": device.client,
                        "last_seen_at": device.last_seen_at,
                        "revoked_at": device.revoked_at,
                        "active_sessions": device.active_session_count,
                    }
                    for device in devices
                ]
            }
        )


class DeviceSessionsRevokeAPIView(SessionAPIBase):
    def delete(self, request, device_id):
        current_id = _require_current_session(request)
        if not current_id:
            return Response(
                {
                    "code": "session_context_required",
                    "detail": "A session-bound authentication token is required for device session management.",
                },
                status=403,
            )

        current_session = UserSession.objects.filter(
            user=request.user,
            session_id=current_id,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).select_related("device").first()
        if current_session is None:
            return Response(
                {
                    "code": "session_invalid",
                    "detail": "The current authentication session is no longer active.",
                },
                status=401,
            )

        target_is_current_device = str(current_session.device.public_id) == str(device_id)
        other_session_on_target_device = False
        if target_is_current_device:
            other_session_on_target_device = UserSession.objects.filter(
                user=request.user,
                device=current_session.device,
                revoked_at__isnull=True,
                expires_at__gt=timezone.now(),
            ).exclude(session_id=current_id).exists()

        if not target_is_current_device or other_session_on_target_device:
            ensure_session_can_revoke_others(
                str(current_id),
                user_id=request.user.id,
            )

        count = invalidate_device(device_id, user_id=request.user.id)
        return Response({"revoked": count})
