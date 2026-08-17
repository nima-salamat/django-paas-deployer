from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Wagtail admin (primary control panel)
    path("admin/", include("wagtail.admin.urls")),
    path("documents/", include("wagtail.documents.urls")),
    # Optional: public Wagtail pages (usually unused in API-first deploy)
    path("pages/", include("wagtail.urls")),

    # Legacy Django admin (staff fallback) — optional
    path("django-admin/", admin.site.urls),

    path("users/", include("users.urls")),
    path("api/users/", include("users.api_urls")),
    path("auth/", include("auth_users.urls")),
    path("plans/", include("plans.urls")),
    path("services/", include("services.urls")),
    path("api/volumes/", include("services.volume_api_urls")),
    path("api/networks/", include("services.network_api_urls")),
    path("deploy/", include("deploy.urls")),
    path("api/system/", include("core.settings_urls")),
    path("media/", include("core.urls")),
    path("api/tickets/", include("tickets.urls")),
    path("api/emails/", include("custom_emails.urls")),
    path("api/messenger/", include("messenger.urls")),
]

# ===DEBUG TRUE===
from django.conf import settings

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # Also serve media files in DEBUG mode for convenience.
    # NOTE: /media/messenger/<path>, /media/images/<path> and /media/tickets/<path>
    # are served by ProtectedMediaView (in core/urls.py) in BOTH debug and
    # production, so this static() entry only matters for other media paths
    # (e.g. /media/deployments/... which has its own authed download endpoint).
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


# Sanitized public error pages. Never expose Django/DRF debug tracebacks or
# infrastructure details to API/web clients when DEBUG is disabled.
handler400 = "core.production_errors.error_400"
handler403 = "core.production_errors.error_403"
handler404 = "core.production_errors.error_404"
handler500 = "core.production_errors.error_500"
