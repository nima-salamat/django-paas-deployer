import os
from django.http import FileResponse, Http404
from django.db import transaction
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import action
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.utils import timezone
from .models import Document, DocumentAsset, DocumentCategory
from .serializers import DocumentSerializer, DocumentAssetSerializer, CategorySerializer

# Public documentation endpoints must remain readable by everyone, including
# anonymous clients and clients that send an expired/invalid Authorization
# header. The global DRF DEFAULT_AUTHENTICATION_CLASSES is JWTAuthentication,
# which raises AuthenticationFailed (HTTP 401) when a Bearer token is present
# but invalid. Setting ``authentication_classes = []`` on the public views
# below means DRF will not attempt JWT validation at all on these routes, so a
# bad token in the request headers can never block anonymous read access.
# Admin write endpoints (DocumentAdminViewSet, CategoryAdminViewSet,
# DocumentAssetListCreateAPIView) keep their JWT + Session authentication.
_PUBLIC_AUTH = []


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
    """Public list of published documentation pages.

    Anonymous access is unconditional: even if a caller sends an invalid or
    expired Bearer token in the Authorization header, the response must still
    be a 200 with the published documents list. ``authentication_classes = []``
    prevents JWTAuthentication from short-circuiting the request with a 401.
    """
    authentication_classes = _PUBLIC_AUTH
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Document.objects.filter(status=Document.Status.PUBLISHED).select_related("category")
        return Response(DocumentSerializer(qs, many=True, context={"request": request}).data)


class PublicCategoryTreeAPIView(APIView):
    authentication_classes = _PUBLIC_AUTH
    permission_classes = [AllowAny]

    def get(self, request):
        categories = list(DocumentCategory.objects.all().order_by("order", "name"))
        published = list(
            Document.objects.filter(status=Document.Status.PUBLISHED)
            .select_related("category")
            .order_by("order", "title")
        )
        docs_by_category = {}
        for doc in published:
            docs_by_category.setdefault(str(doc.category_id) if doc.category_id else None, []).append(
                DocumentSerializer(doc, context={"request": request}).data
            )
        children = {}
        for cat in categories:
            children.setdefault(str(cat.parent_id) if cat.parent_id else None, []).append(cat)

        def build(parent):
            result = []
            for cat in children.get(parent, []):
                result.append({
                    **CategorySerializer(cat, context={"request": request}).data,
                    "documents": docs_by_category.get(str(cat.id), []),
                    "children": build(str(cat.id)),
                })
            return result

        return Response({"categories": build(None), "uncategorized": docs_by_category.get(None, [])})


class PublicDocumentDetailAPIView(APIView):
    authentication_classes = _PUBLIC_AUTH
    permission_classes = [AllowAny]

    def get(self, request, slug):
        try:
            obj = Document.objects.select_related("category").prefetch_related("assets").get(
                slug=slug, status=Document.Status.PUBLISHED
            )
        except Document.DoesNotExist:
            return Response({"detail": "Documentation page not found."}, status=404)
        return Response(DocumentSerializer(obj, context={"request": request}).data)


class CategoryAdminViewSet(ModelViewSet):
    queryset = DocumentCategory.objects.all().select_related("parent")
    serializer_class = CategorySerializer
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated, DocsManagePermission]

    def destroy(self, request, *args, **kwargs):
        # Deleting a category must never orphan its content or unexpectedly
        # delete an entire subtree. Move documents and direct child
        # categories to the deleted category's parent first.
        category = self.get_object()
        parent = category.parent
        with transaction.atomic():
            Document.objects.filter(category=category).update(category=parent)
            DocumentCategory.objects.filter(parent=category).update(parent=parent)
            category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def tree(self, request):
        nodes = list(self.get_queryset())
        by_parent = {}
        for node in nodes:
            by_parent.setdefault(str(node.parent_id) if node.parent_id else None, []).append(node)

        # Attach all documents (draft + published) so the admin tree is complete.
        docs = list(
            Document.objects.all()
            .select_related("category")
            .order_by("order", "title")
        )
        docs_by_cat = {}
        for doc in docs:
            key = str(doc.category_id) if doc.category_id else None
            docs_by_cat.setdefault(key, []).append(
                DocumentSerializer(doc, context={"request": request}).data
            )

        def build(parent_id):
            result = []
            for node in by_parent.get(parent_id, []):
                item = CategorySerializer(node, context={"request": request}).data
                item["documents"] = docs_by_cat.get(str(node.id), [])
                item["children"] = build(str(node.id))
                result.append(item)
            return result

        return Response({
            "categories": build(None),
            "uncategorized": docs_by_cat.get(None, []),
        })


class DocumentAdminViewSet(ModelViewSet):
    queryset = Document.objects.all().select_related("category").prefetch_related("assets")
    serializer_class = DocumentSerializer
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated, DocsManagePermission]

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


class DocumentAssetPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 48


class DocumentAssetListCreateAPIView(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated, DocsManagePermission]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        qs = DocumentAsset.objects.all().select_related("document")
        kind = (request.query_params.get("kind") or "").strip()
        search = (request.query_params.get("search") or "").strip()
        if kind:
            qs = qs.filter(kind=kind)
        if search:
            qs = qs.filter(name__icontains=search)
        paginator = DocumentAssetPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer_data = DocumentAssetSerializer(page, many=True, context={"request": request}).data
        response = paginator.get_paginated_response(serializer_data)
        response.data["page"] = paginator.page.number
        response.data["page_size"] = paginator.get_page_size(request)
        response.data["pages"] = paginator.page.paginator.num_pages
        return response

    def post(self, request):
        incoming = request.FILES.get("file")
        if not incoming:
            return Response({"detail": "file is required."}, status=400)
        document = None
        doc_id = request.data.get("document")
        if doc_id:
            document = Document.objects.filter(pk=doc_id).first()
            if not document:
                return Response({"detail": "Document not found."}, status=404)
        asset = DocumentAsset(document=document, file=incoming, alt=str(request.data.get("alt") or "")[:240])
        try:
            asset.full_clean()
            asset.save()
        except Exception as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(DocumentAssetSerializer(asset, context={"request": request}).data, status=201)


class DocumentAssetAPIView(APIView):
    """Serve assets referenced by the public documentation.

    GET is completely public (no authentication at all).
    Only assets that belong to a *published* document are served.
    Mutating methods remain admin-only.
    """

    authentication_classes = []

    def get_authenticators(self):
        # فقط برای متدهای غیر از GET/HEAD authentication داشته باشیم
        if self.request.method in {"GET", "HEAD"}:
            return []
        return [
            JWTAuthentication(),
            SessionAuthentication(),
        ]

    def get_permissions(self):
        if self.request.method in {"GET", "HEAD"}:
            return [AllowAny()]
        return [IsAuthenticated(), DocsManagePermission()]

    @staticmethod
    def _serve_asset(asset, public=False):
        if not asset.file:
            raise Http404
        response = FileResponse(
            asset.file.open("rb"),
            content_type=asset.mime_type or "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = (
            "inline"
            if asset.kind in {"image", "audio", "video"}
            else f'attachment; filename="{os.path.basename(asset.name)}"'
        )
        response["Cache-Control"] = "public, max-age=86400" if public else "private, no-store"
        return response

    def get(self, request, asset_id):
        try:
            asset = DocumentAsset.objects.select_related("document").get(pk=asset_id)
        except DocumentAsset.DoesNotExist:
            raise Http404

        # فقط assetهای مربوط به داکیومنت published عمومی هستند
        if not asset.document_id or asset.document.status != Document.Status.PUBLISHED:
            raise Http404
        return self._serve_asset(asset, public=True)

    def delete(self, request, asset_id):
        try:
            asset = DocumentAsset.objects.get(pk=asset_id)
        except DocumentAsset.DoesNotExist:
            raise Http404
        if asset.file:
            try:
                asset.file.delete(save=False)
            except Exception:
                pass
        asset.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, asset_id):
        """Reassign asset to a document or update alt/name."""
        try:
            asset = DocumentAsset.objects.select_related("document").get(pk=asset_id)
        except DocumentAsset.DoesNotExist:
            raise Http404
        doc_id = request.data.get("document", "__unset__")
        if doc_id != "__unset__":
            if doc_id in (None, "", "null"):
                asset.document = None
            else:
                document = Document.objects.filter(pk=doc_id).first()
                if not document:
                    return Response({"detail": "Document not found."}, status=404)
                asset.document = document
        if "alt" in request.data:
            asset.alt = str(request.data.get("alt") or "")[:240]
        if "name" in request.data and request.data.get("name"):
            asset.name = str(request.data.get("name"))[:255]
        asset.save()
        return Response(DocumentAssetSerializer(asset, context={"request": request}).data)


class DocumentAssetAdminPreviewAPIView(APIView):
    """Authenticated media read for the Admin Docs media library/editor."""

    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated, DocsManagePermission]

    def get(self, request, asset_id):
        try:
            asset = DocumentAsset.objects.get(pk=asset_id)
        except DocumentAsset.DoesNotExist:
            raise Http404
        return DocumentAssetAPIView._serve_asset(asset, public=False)