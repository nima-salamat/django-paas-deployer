from pathlib import Path

from django.http import FileResponse, Http404
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from deploy.models import Deploy


class DeploymentDownloadAPIView(APIView):
    authentication_classes = [
        SessionAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request, pk):
        deploy = (
            Deploy.objects
            .select_related("service", "service__user")
            .filter(pk=pk)
            .first()
        )

        if not deploy:
            raise Http404("Deployment not found.")

        user = request.user
        is_admin = user.is_staff or user.is_superuser
        is_owner = (
            deploy.service_id
            and getattr(deploy.service, "user_id", None) == user.id
        )

        if not (is_admin or is_owner):
            raise Http404("Deployment not found.")

        if not deploy.zip_file:
            raise Http404("No ZIP file available for this deployment.")

        if not deploy.zip_file.storage.exists(deploy.zip_file.name):
            raise Http404("ZIP file not found on storage.")

        try:
            file_handle = deploy.zip_file.open("rb")
        except Exception:
            raise Http404("ZIP file not accessible.")

        filename = Path(deploy.zip_file.name).name

        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=filename,
            content_type="application/zip",
        )

        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"

        return response


class ProtectedMediaView(APIView):
    """Serve media files from MEDIA_ROOT with JWT auth.

    Accepts Authorization: Bearer <token> header OR ?token=<token> query.
    Used for group avatars, user profile photos, ticket attachments and
    other media that <img> tags can't auth with headers.

    Mounted at multiple URLs (see core/urls.py):
      /media/messenger/<path:path>  → group avatars + message attachments
      /media/images/<path:path>     → user profile photos
      /media/tickets/<path:path>    → ticket attachments
    """

    # No authentication_classes / permission_classes: we authenticate manually
    # so we can accept ?token= query (which the standard DRF JWT auth doesn't).

    # Allowed path prefixes under MEDIA_ROOT. Anything outside these is 404.
    ALLOWED_PREFIXES = ("messenger/", "images/", "tickets/")

    def _authenticate(self, request):
        from rest_framework_simplejwt.tokens import AccessToken
        from django.contrib.auth import get_user_model

        User = get_user_model()
        # 1. Authorization header
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if auth.startswith("Bearer "):
            tok = auth[7:].strip()
            try:
                access = AccessToken(tok)
                user_id = access.get("user_id") or access.get("user")
                if user_id:
                    return User.objects.filter(pk=user_id).first()
            except Exception:
                return None
        # 2. ?token= query
        tok = request.GET.get("token")
        if tok:
            try:
                access = AccessToken(tok)
                user_id = access.get("user_id") or access.get("user")
                if user_id:
                    return User.objects.filter(pk=user_id).first()
            except Exception:
                return None
        # 3. Session auth (logged-in via browser)
        if request.user and request.user.is_authenticated:
            return request.user
        return None

    def get(self, request, path):
        from django.conf import settings

        user = self._authenticate(request)
        if not user:
            # Return JSON 404 so the frontend can detect the failure cleanly
            # (an <img> tag will fire onerror and the UI can show a fallback).
            from rest_framework.response import Response
            from rest_framework import status as drf_status
            return Response(
                {"detail": "Authentication required."},
                status=drf_status.HTTP_404_NOT_FOUND,
            )

        # Allow only whitelisted prefixes (prevents serving arbitrary files
        # from MEDIA_ROOT — e.g. deployment zips, which have their own authed
        # download endpoint).
        if not any(path.startswith(p) for p in self.ALLOWED_PREFIXES):
            from rest_framework.response import Response
            from rest_framework import status as drf_status
            return Response(
                {"detail": "Not found."},
                status=drf_status.HTTP_404_NOT_FOUND,
            )

        media_root = Path(settings.MEDIA_ROOT).resolve()
        # Normalize and prevent directory traversal. We do NOT use
        # resolve(strict=True) because that raises if the file doesn't exist
        # — but we want to fall through to the is_file() check below so the
        # error path is uniform.
        try:
            full_path = (media_root / path).resolve()
        except Exception:
            from rest_framework.response import Response
            from rest_framework import status as drf_status
            return Response(
                {"detail": "Not found."},
                status=drf_status.HTTP_404_NOT_FOUND,
            )

        # Confirm the resolved path is still inside MEDIA_ROOT (prevents ../../).
        try:
            full_path.relative_to(media_root)
        except ValueError:
            from rest_framework.response import Response
            from rest_framework import status as drf_status
            return Response(
                {"detail": "Not found."},
                status=drf_status.HTTP_404_NOT_FOUND,
            )

        if not full_path.is_file():
            # File no longer exists on disk (e.g. deleted profile photo, stale
            # URL cached in the client). Return a clean 404 — the frontend
            # should detect this and show the fallback avatar (initial letter).
            from rest_framework.response import Response
            from rest_framework import status as drf_status
            return Response(
                {"detail": "File not found."},
                status=drf_status.HTTP_404_NOT_FOUND,
            )

        # Detect content type
        ext = full_path.suffix.lower()
        ct_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif",
            ".webp": "image/webp", ".bmp": "image/bmp",
            ".mp4": "video/mp4", ".webm": "video/webm",
            ".mov": "video/quicktime",
            ".mp3": "audio/mpeg", ".ogg": "audio/ogg",
            ".wav": "audio/wav", ".m4a": "audio/mp4", ".aac": "audio/aac",
            ".pdf": "application/pdf",
            ".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv",
            ".json": "application/json",
        }
        content_type = ct_map.get(ext, "application/octet-stream")

        try:
            fh = open(str(full_path), "rb")
        except Exception:
            from rest_framework.response import Response
            from rest_framework import status as drf_status
            return Response(
                {"detail": "File not accessible."},
                status=drf_status.HTTP_404_NOT_FOUND,
            )

        # Content-Disposition: inline for inline viewing (images/videos/audio),
        # attachment for everything else (downloads).
        inline_exts = {
            ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
            ".mp4", ".webm", ".mov",
            ".mp3", ".ogg", ".wav", ".m4a", ".aac",
            ".pdf",
        }
        disposition = "inline" if ext in inline_exts else "attachment"

        resp = FileResponse(fh, content_type=content_type)
        # Cache for 1 hour on the client (URL contains a unique uuid so caching
        # is safe — a new avatar upload will produce a new URL).
        resp["Cache-Control"] = "public, max-age=3600"
        resp["Expires"] = "3600"
        resp["Content-Disposition"] = f'{disposition}; filename="{full_path.name}"'
        # Support HTTP Range requests for media (seeking in video/audio)
        # — FileResponse already handles this on Django >= 4.2 if the file
        # supports seek(), but we set the header explicitly to be safe.
        resp["Accept-Ranges"] = "bytes"
        return resp
