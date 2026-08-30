from django.contrib import admin
from .models import Document, DocumentAsset

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "section", "status", "order", "updated_at")
    search_fields = ("title", "slug", "description", "section")
    list_filter = ("status", "section")
    prepopulated_fields = {"slug": ("title",)}

@admin.register(DocumentAsset)
class DocumentAssetAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "alt", "created_at")
    search_fields = ("document__title", "alt")
