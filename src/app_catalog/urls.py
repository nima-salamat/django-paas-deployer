from django.urls import path
from .apis import (
    CatalogListAPIView,
    CatalogDetailAPIView,
    CatalogResolveAPIView,
    ApplicationInstanceListCreateAPIView,
    ApplicationInstanceDetailAPIView,
    ApplicationInstanceCancelAPIView,
)

urlpatterns = [
    path("apps/", CatalogListAPIView.as_view(), name="application-catalog-list"),
    path("apps/<str:catalog_id>/", CatalogDetailAPIView.as_view(), name="application-catalog-detail"),
    path("apps/<str:catalog_id>/resolve/", CatalogResolveAPIView.as_view(), name="application-catalog-resolve"),
    path("installations/", ApplicationInstanceListCreateAPIView.as_view(), name="application-installation-list-create"),
    path("installations/<uuid:pk>/", ApplicationInstanceDetailAPIView.as_view(), name="application-installation-detail"),
    path("installations/<uuid:pk>/cancel/", ApplicationInstanceCancelAPIView.as_view(), name="application-installation-cancel"),
]
