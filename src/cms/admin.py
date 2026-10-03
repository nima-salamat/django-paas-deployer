from django.contrib import admin

from core.django_admin import ReadOnlyProjectModelAdmin
from .models import HomePage


@admin.register(HomePage)
class HomePageAdmin(ReadOnlyProjectModelAdmin):
    list_display = ("title", "slug", "depth", "live", "last_published_at")
    search_fields = ("title", "slug")
    readonly_fields = ("title", "slug", "depth", "path", "url_path", "live", "last_published_at", "first_published_at", "body")
