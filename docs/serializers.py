from rest_framework import serializers
from .models import Document, DocumentAsset

ALLOWED_BLOCKS = {
    "heading": {"level", "text"},
    "paragraph": {"text"},
    "list": {"ordered", "items"},
    "code": {"language", "code", "filename"},
    "image": {"asset_id", "alt", "caption"},
    "callout": {"tone", "title", "text"},
    "quote": {"text", "author"},
    "link": {"label", "url", "description"},
    "divider": set(),
}


def clean_blocks(value):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 250:
        raise serializers.ValidationError("content must be a list with at most 250 blocks.")
    out = []
    for block in value:
        if not isinstance(block, dict):
            raise serializers.ValidationError("Every content block must be an object.")
        kind = str(block.get("type") or "").strip().lower()
        if kind not in ALLOWED_BLOCKS:
            raise serializers.ValidationError(f"Unsupported block type: {kind or 'empty'}")
        allowed = ALLOWED_BLOCKS[kind]
        clean = {"type": kind}
        for key in allowed:
            if key in block:
                clean[key] = block[key]
        if kind == "heading":
            level = int(clean.get("level", 2))
            if level not in (1, 2, 3):
                raise serializers.ValidationError("Heading level must be 1, 2 or 3.")
            clean["level"] = level
            clean["text"] = str(clean.get("text", ""))[:1000]
        elif kind in ("paragraph", "quote", "callout"):
            clean["text"] = str(clean.get("text", ""))[:12000]
        elif kind == "list":
            items = clean.get("items", [])
            if not isinstance(items, list) or len(items) > 100:
                raise serializers.ValidationError("List items are invalid.")
            clean["items"] = [str(x)[:2000] for x in items]
            clean["ordered"] = bool(clean.get("ordered", False))
        elif kind == "code":
            clean["language"] = str(clean.get("language", "text"))[:32]
            clean["filename"] = str(clean.get("filename", ""))[:180]
            clean["code"] = str(clean.get("code", ""))[:50000]
        elif kind == "image":
            clean["asset_id"] = str(clean.get("asset_id", ""))[:64]
            clean["alt"] = str(clean.get("alt", ""))[:240]
            clean["caption"] = str(clean.get("caption", ""))[:500]
        elif kind == "callout":
            tone = str(clean.get("tone", "info"))
            clean["tone"] = tone if tone in {"info", "success", "warning", "danger"} else "info"
            clean["title"] = str(clean.get("title", ""))[:240]
        elif kind == "link":
            url = str(clean.get("url", ""))[:2000]
            if not (url.startswith("https://") or url.startswith("http://") or url.startswith("/")):
                raise serializers.ValidationError("Links must use http(s) or an internal path.")
            clean["url"] = url
            clean["label"] = str(clean.get("label", ""))[:240]
            clean["description"] = str(clean.get("description", ""))[:500]
        out.append(clean)
    return out


class DocumentAssetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = DocumentAsset
        fields = ("id", "alt", "url", "created_at")

    def get_url(self, obj):
        request = self.context.get("request")
        path = f"/api/docs/assets/{obj.id}/"
        return request.build_absolute_uri(path) if request else path


class DocumentSerializer(serializers.ModelSerializer):
    assets = DocumentAssetSerializer(many=True, read_only=True)

    class Meta:
        model = Document
        fields = (
            "id", "title", "slug", "description", "section", "icon", "order",
            "status", "content", "assets", "created_at", "updated_at", "published_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "published_at")

    def validate_content(self, value):
        cleaned = clean_blocks(value)
        # Existing assets may only be referenced by the document that owns them.
        # During initial creation the document has no PK/assets yet; those image
        # blocks are completed by the upload endpoint after the document is saved.
        if getattr(self.instance, "pk", None):
            asset_ids = {
                block.get("asset_id")
                for block in cleaned
                if block.get("type") == "image" and block.get("asset_id")
            }
            if asset_ids:
                own = set(str(x) for x in DocumentAsset.objects.filter(
                    document=self.instance, id__in=asset_ids
                ).values_list("id", flat=True))
                foreign = asset_ids - own
                if foreign:
                    raise serializers.ValidationError("An image block references an asset owned by another document.")
        return cleaned

    def validate_slug(self, value):
        value = str(value).strip().lower()
        if not value:
            raise serializers.ValidationError("Slug is required.")
        return value
