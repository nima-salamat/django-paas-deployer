"""REST API for system settings (staff / superuser)."""
from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from core.models import SystemSetting
from core import settings_service as svc


class SystemSettingListAPIView(APIView):
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        category = request.query_params.get("category")
        rows = svc.all_settings(include_secrets=True)
        if category:
            rows = [r for r in rows if r["category"] == category]
        return Response({"count": len(rows), "results": rows})


class SystemSettingDetailAPIView(APIView):
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request, key: str):
        row = SystemSetting.objects.filter(key=key).first()
        if not row:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "key": row.key,
                "value": row.cast_value(),
                "raw_value": row.value,
                "value_type": row.value_type,
                "category": row.category,
                "label": row.label,
                "description": row.description,
                "is_secret": row.is_secret,
                "is_editable": row.is_editable,
                "updated_at": row.updated_at,
            }
        )

    def patch(self, request, key: str):
        row = SystemSetting.objects.filter(key=key).first()
        if not row:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not row.is_editable and not request.user.is_superuser:
            return Response(
                {"detail": "Setting is locked."}, status=status.HTTP_403_FORBIDDEN
            )
        if "value" not in request.data:
            return Response(
                {"detail": "Field 'value' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ok = svc.set_setting(key, request.data["value"], actor=str(request.user))
        if not ok:
            return Response(
                {"detail": "Update failed."}, status=status.HTTP_400_BAD_REQUEST
            )
        row.refresh_from_db()
        return Response({"key": row.key, "value": row.cast_value(), "ok": True})


class SystemSettingSeedAPIView(APIView):
    """POST → seed missing keys from code defaults (superuser)."""

    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request):
        if not request.user.is_superuser:
            return Response(status=status.HTTP_403_FORBIDDEN)
        from core.initial_config import (
            seed_system_settings,
            seed_dockerfile_templates_from_config,
        )

        update = bool(request.data.get("update_existing"))
        n = seed_system_settings(update_existing=update)
        d = seed_dockerfile_templates_from_config()
        return Response({"created_settings": n, "created_dockerfiles": d})
