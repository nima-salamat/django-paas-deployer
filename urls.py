from django.contrib import admin
from django.urls import path

urlpatterns = [
    path('admin/', admin.site.urls),
]

# ===DENUG TRUE===
from django.conf import settings

if settings.DEBUG:
    from django.urls import re_path
    from django.conf.urls.static import static
    
    urlpatterns += static(settings.STATIC_URL, document_root= settings.STATIC_ROOT)
