from django.urls import path
from rest_framework.routers import DefaultRouter
from .apis import (
    PublicDocumentsAPIView, PublicCategoryTreeAPIView, PublicDocumentDetailAPIView,
    DocumentAdminViewSet, CategoryAdminViewSet, DocumentAssetListCreateAPIView, DocumentAssetAPIView, DocumentAssetAdminPreviewAPIView,
)

router = DefaultRouter()
router.register(r"admin/documents", DocumentAdminViewSet, basename="docs-admin")
router.register(r"admin/categories", CategoryAdminViewSet, basename="docs-categories")

urlpatterns = [
    path("", PublicDocumentsAPIView.as_view(), name="docs-list"),
    path("tree/", PublicCategoryTreeAPIView.as_view(), name="docs-tree"),
    path("public/<slug:slug>/", PublicDocumentDetailAPIView.as_view(), name="docs-detail"),
    path("admin/assets/", DocumentAssetListCreateAPIView.as_view(), name="docs-assets-list-create"),
    path("admin/assets/<uuid:asset_id>/", DocumentAssetAdminPreviewAPIView.as_view(), name="docs-admin-asset-preview"),
    path("assets/<uuid:asset_id>/", DocumentAssetAPIView.as_view(), name="docs-asset"),
] + router.urls
