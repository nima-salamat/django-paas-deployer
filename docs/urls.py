from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .apis import PublicDocumentsAPIView, PublicDocumentDetailAPIView, DocumentAdminViewSet, DocumentAssetCreateAPIView, DocumentAssetAPIView

router = DefaultRouter()
router.register(r"admin/documents", DocumentAdminViewSet, basename="docs-admin")

urlpatterns = [
    path("", PublicDocumentsAPIView.as_view(), name="docs-list"),
    path("public/<slug:slug>/", PublicDocumentDetailAPIView.as_view(), name="docs-detail"),
    path("admin/documents/<uuid:document_id>/assets/", DocumentAssetCreateAPIView.as_view(), name="docs-assets-create"),
    path("assets/<uuid:asset_id>/", DocumentAssetAPIView.as_view(), name="docs-asset"),
] + router.urls
