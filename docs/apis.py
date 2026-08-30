import mimetypes
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import action
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Document, DocumentAsset
from .serializers import DocumentSerializer, DocumentAssetSerializer


def has_rule(user, code):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    try:
        return bool(user.is_staff and code in (user.rule.rules or []))
    except Exception:
        return False


class DocsManagePermission(BasePermission):
    def has_permission(self, request, view):
        return has_rule(request.user, "docs.manage")


class PublicDocumentsAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Document.objects.filter(status=Document.Status.PUBLISHED).prefetch_related("assets")
        section = (request.query_params.get("section") or "").strip()
        if section:
            qs = qs.filter(section=section)
        return Response(DocumentSerializer(qs, many=True, context={"request": request}).data)


class PublicDocumentDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            obj = Document.objects.prefetch_related("assets").get(slug=slug, status=Document.Status.PUBLISHED)
        except Document.DoesNotExist:
            return Response({"detail": "Documentation page not found."}, status=404)
        return Response(DocumentSerializer(obj, context={"request": request}).data)


class DocumentAdminViewSet(ModelViewSet):
    queryset = Document.objects.all().prefetch_related("assets")
    serializer_class = DocumentSerializer
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated, DocsManagePermission]

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        obj = self.get_object()
        obj.status = Document.Status.PUBLISHED
        obj.published_at = obj.published_at or timezone.now()
        obj.save(update_fields=["status", "published_at", "updated_at"])
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        obj = self.get_object()
        obj.status = Document.Status.DRAFT
        obj.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(obj).data)


class DocumentAssetCreateAPIView(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated, DocsManagePermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, document_id):
        try:
            document = Document.objects.get(pk=document_id)
        except Document.DoesNotExist:
            return Response({"detail": "Document not found."}, status=404)
        image = request.FILES.get("image")
        if not image:
            return Response({"detail": "image is required."}, status=400)
        asset = DocumentAsset(document=document, image=image, alt=str(request.data.get("alt") or "")[:240])
        try:
            asset.full_clean()
            asset.save()
        except Exception as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(DocumentAssetSerializer(asset, context={"request": request}).data, status=201)


class DocumentAssetAPIView(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request, asset_id):
        try:
            asset = DocumentAsset.objects.select_related("document").get(pk=asset_id)
        except DocumentAsset.DoesNotExist:
            raise Http404
        if asset.document.status != Document.Status.PUBLISHED and not has_rule(request.user, "docs.manage"):
            return Response({"detail": "Not found."}, status=404)
        if not asset.image:
            raise Http404
        # Images are verified at upload time, but serve them as images rather
        # than trusting an attacker-controlled filename extension.
        content_type = "application/octet-stream"
        try:
            from PIL import Image as PILImage
            with PILImage.open(asset.image.file) as checked:
                fmt = (checked.format or "").upper()
            content_type = {
                "JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp",
                "GIF": "image/gif", "SVG": "image/svg+xml",
            }.get(fmt, content_type)
            asset.image.seek(0)
        except Exception:
            pass
        response = FileResponse(asset.image.open("rb"), content_type=content_type)
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "public, max-age=86400" if asset.document.status == Document.Status.PUBLISHED else "private, no-store"
        return response
