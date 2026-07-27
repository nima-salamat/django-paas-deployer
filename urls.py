from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path("users/", include("users.urls")),
    path("api/users/", include("users.api_urls")),
    path("auth/", include("auth_users.urls")),
    path("plans/", include("plans.urls")),
    path("services/", include("services.urls")),
    path("api/volumes/", include("services.volume_api_urls")),
    path("api/networks/", include("services.network_api_urls")),
    path("deploy/", include("deploy.urls")),
    
]

# ===DENUG TRUE===
from django.conf import settings

if settings.DEBUG:
    from django.urls import re_path
    from django.conf.urls.static import static
    
    urlpatterns += static(settings.STATIC_URL, document_root= settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)