from rest_framework import serializers
from .models import Document, DocumentAsset, DocumentCategory


class CategorySerializer(serializers.ModelSerializer):
    parent_id = serializers.UUIDField(source="parent.id", read_only=True)

    class Meta:
        model = DocumentCategory
        fields = ("id", "name", "slug", "parent", "parent_id", "description", "icon", "order")
        read_only_fields = ("id", "parent_id")


class DocumentAssetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    document_status = serializers.SerializerMethodField()

    class Meta:
        model = DocumentAsset
        fields = ("id", "document", "document_status", "name", "alt", "kind", "mime_type", "size_bytes", "url", "created_at")
        read_only_fields = ("id", "kind", "mime_type", "size_bytes", "url", "created_at")

    def get_document_status(self, obj):
        return obj.document.status if obj.document_id else None

    def get_url(self, obj):
        request = self.context.get("request")
        path = f"/api/docs/assets/{obj.id}/"
        return request.build_absolute_uri(path) if request else path


class DocumentSerializer(serializers.ModelSerializer):
    assets = DocumentAssetSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Document
        fields = (
            "id", "title", "slug", "description", "category", "category_name", "icon", "order",
            "status", "content", "assets", "created_at", "updated_at", "published_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "published_at")

    def validate_content(self, value):
        if not isinstance(value, str):
            raise serializers.ValidationError("content must be Markdown text.")
        if len(value) > 500_000:
            raise serializers.ValidationError("Markdown document is too large (500 KB max).")
        return value


class DocumentCreateSerializer(DocumentSerializer):
    class Meta(DocumentSerializer.Meta):
        pass
