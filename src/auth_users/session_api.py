from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SessionJWTAuthentication
from .models import Device, UserSession
from .session_auth import invalidate_all_sessions, invalidate_device, invalidate_session


class SessionAPIBase(APIView):
    authentication_classes = [SessionJWTAuthentication]
    permission_classes = [IsAuthenticated]


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
        sessions = UserSession.objects.filter(
            user=request.user, revoked_at__isnull=True
        ).select_related("device").order_by("-last_seen_at")
        return Response({"results": [_session_payload(s, current_id) for s in sessions]})


class SessionRevokeAPIView(SessionAPIBase):
    def delete(self, request, session_id):
        session = UserSession.objects.filter(user=request.user, session_id=session_id).first()
        if session is None:
            return Response({"detail": "Session not found."}, status=404)
        invalidate_session(session.session_id)
        return Response(status=204)


class SessionLogoutAllAPIView(SessionAPIBase):
    def post(self, request):
        count = invalidate_all_sessions(request.user.id)
        return Response({"revoked": count})


class DeviceListAPIView(SessionAPIBase):
    def get(self, request):
        devices = Device.objects.filter(user=request.user).order_by("-last_seen_at")
        return Response({
            "results": [
                {
                    "id": str(device.public_id),
                    "name": device.name,
                    "platform": device.platform,
                    "client": device.client,
                    "last_seen_at": device.last_seen_at,
                    "revoked_at": device.revoked_at,
                    "active_sessions": device.sessions.filter(revoked_at__isnull=True).count(),
                }
                for device in devices
            ]
        })


class DeviceSessionsRevokeAPIView(SessionAPIBase):
    def delete(self, request, device_id):
        count = invalidate_device(device_id, user_id=request.user.id)
        return Response({"revoked": count})
