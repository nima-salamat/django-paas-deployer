from django.contrib import admin
from .models import Document, DocumentAsset, DocumentCategory

@admin.register(DocumentCategory)
class DocumentCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "order", "updated_at")
    search_fields = ("name", "slug", "description")
    list_filter = ("parent",)
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "status", "order", "updated_at")
    search_fields = ("title", "slug", "description")
    list_filter = ("status", "category")
    prepopulated_fields = {"slug": ("title",)}

@admin.register(DocumentAsset)
class DocumentAssetAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "document", "size_bytes", "created_at")
    search_fields = ("name", "alt", "mime_type")
    list_filter = ("kind",)
