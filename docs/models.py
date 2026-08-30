import os
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


def document_asset_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()[:12]
    return f"docs/assets/{instance.document_id}/{uuid.uuid4().hex}{ext}"


class Document(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.CharField(max_length=320, blank=True, default="")
    section = models.CharField(max_length=100, blank=True, default="Documentation")
    icon = models.CharField(max_length=64, blank=True, default="description")
    order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    content = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("section", "order", "title")

    def clean(self):
        if not isinstance(self.content, list):
            raise ValidationError({"content": "Content must be a list of blocks."})
        if len(self.content) > 250:
            raise ValidationError({"content": "A document may contain at most 250 blocks."})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:220]
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class DocumentAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, related_name="assets", on_delete=models.CASCADE)
    image = models.ImageField(upload_to=document_asset_path)
    alt = models.CharField(max_length=240, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        image = self.image
        if not image:
            raise ValidationError({"image": "Image is required."})
        content_type = getattr(image, "content_type", "") or ""
        if content_type and not content_type.startswith("image/"):
            raise ValidationError({"image": "Only image files are allowed."})
        if getattr(image, "size", 0) > 8 * 1024 * 1024:
            raise ValidationError({"image": "Image must be 8 MB or smaller."})
        # Verify bytes with Pillow; never trust the browser supplied MIME type.
        try:
            from PIL import Image as PILImage
            image.file.seek(0)
            with PILImage.open(image.file) as checked:
                checked.verify()
            image.file.seek(0)
            image.format = getattr(checked, "format", None)
        except Exception as exc:
            raise ValidationError({"image": f"The uploaded file is not a valid image: {exc}"}) from exc

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
