import os
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import action
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.utils import timezone
from .models import Document, DocumentAsset, DocumentCategory
from .serializers import DocumentSerializer, DocumentAssetSerializer, CategorySerializer


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
        qs = Document.objects.filter(status=Document.Status.PUBLISHED).select_related("category")
        return Response(DocumentSerializer(qs, many=True, context={"request": request}).data)


class PublicCategoryTreeAPIView(APIView):
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
        return Response(DocumentAssetSerializer(qs[:500], many=True, context={"request": request}).data)

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
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request, asset_id):
        try:
            asset = DocumentAsset.objects.select_related("document").get(pk=asset_id)
        except DocumentAsset.DoesNotExist:
            raise Http404

        # Browser media tags (<img>, <audio>, <video>) cannot attach an
        # Authorization header. Admin previews therefore may provide the same
        # short-lived JWT in ?token=. Never treat an arbitrary token as public
        # access: it must authenticate through SimpleJWT and still pass the
        # docs.manage rule below.
        if not request.user.is_authenticated:
            raw_token = (request.query_params.get("token") or "").strip()
            if raw_token:
                try:
                    jwt_auth = JWTAuthentication()
                    validated = jwt_auth.get_validated_token(raw_token)
                    request.user = jwt_auth.get_user(validated)
                except Exception:
                    pass

        # Unattached/draft assets are private library objects. Only assets
        # belonging to a published document are public.
        if not asset.document_id:
            if not has_rule(request.user, "docs.manage"):
                raise Http404
        elif asset.document.status != Document.Status.PUBLISHED and not has_rule(request.user, "docs.manage"):
            raise Http404
        if not asset.file:
            raise Http404
        response = FileResponse(asset.file.open("rb"), content_type=asset.mime_type or "application/octet-stream")
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = "inline" if asset.kind in {"image", "audio", "video"} else f'attachment; filename="{os.path.basename(asset.name)}"'
        response["Cache-Control"] = "public, max-age=86400" if asset.document_id and asset.document.status == Document.Status.PUBLISHED else "private, no-store"
        return response

    def delete(self, request, asset_id):
        if not has_rule(request.user, "docs.manage"):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
        try:
            asset = DocumentAsset.objects.get(pk=asset_id)
        except DocumentAsset.DoesNotExist:
            raise Http404
        # Remove the file from storage, then the row.
        if asset.file:
            try:
                asset.file.delete(save=False)
            except Exception:
                pass
        asset.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, asset_id):
        """Reassign asset to a document or update alt/name."""
        if not has_rule(request.user, "docs.manage"):
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
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
