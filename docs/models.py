import mimetypes
import os
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


def document_asset_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()[:12]
    return f"docs/assets/{uuid.uuid4().hex}{ext}"


class DocumentCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=140)
    slug = models.SlugField(max_length=180, unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, related_name="children", on_delete=models.CASCADE
    )
    description = models.CharField(max_length=320, blank=True, default="")
    icon = models.CharField(max_length=64, blank=True, default="folder")
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("order", "name")
        constraints = [
            models.UniqueConstraint(fields=("parent", "name"), name="docs_category_parent_name_uniq"),
        ]

    def clean(self):
        if self.parent_id:
            seen = {self.pk}
            node = self.parent
            while node is not None:
                if node.pk in seen:
                    raise ValidationError({"parent": "A category cannot be its own ancestor."})
                seen.add(node.pk)
                node = node.parent

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:180]
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Document(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.CharField(max_length=320, blank=True, default="")
    category = models.ForeignKey(
        DocumentCategory, null=True, blank=True, related_name="documents", on_delete=models.SET_NULL
    )
    icon = models.CharField(max_length=64, blank=True, default="description")
    order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    # Markdown is the source of truth. Rendering is handled by the frontend.
    content = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("order", "title")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:220]
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class DocumentAsset(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        AUDIO = "audio", "Audio"
        FILE = "file", "File"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document, related_name="assets", null=True, blank=True, on_delete=models.SET_NULL
    )
    file = models.FileField(upload_to=document_asset_path)
    name = models.CharField(max_length=255, blank=True, default="")
    alt = models.CharField(max_length=240, blank=True, default="")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.FILE)
    mime_type = models.CharField(max_length=120, blank=True, default="")
    size_bytes = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def clean(self):
        if not self.file:
            raise ValidationError({"file": "A file is required."})
        size = getattr(self.file, "size", 0) or 0
        if size > 50 * 1024 * 1024:
            raise ValidationError({"file": "Files must be 50 MB or smaller."})

        filename = getattr(self.file, "name", "") or ""
        ext = os.path.splitext(filename)[1].lower()
        content_type = (
            getattr(self.file, "content_type", "")
            or self.mime_type
            or mimetypes.guess_type(filename)[0]
            or ""
        ).lower()
        # Some reverse proxies / clients report application/octet-stream for
        # multipart uploads. Resolve a safe MIME type from the extension so
        # valid images/audio/video are classified correctly.
        mime_by_ext = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp",
            ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
            ".m4v": "video/x-m4v", ".mp3": "audio/mpeg", ".wav": "audio/wav",
            ".ogg": "audio/ogg", ".m4a": "audio/mp4",
        }
        if (not content_type or content_type == "application/octet-stream") and ext in mime_by_ext:
            content_type = mime_by_ext[ext]
        if content_type.startswith("image/"):
            self.kind = self.Kind.IMAGE
            try:
                from PIL import Image as PILImage
                self.file.seek(0)
                with PILImage.open(self.file) as checked:
                    checked.verify()
                self.file.seek(0)
            except Exception as exc:
                raise ValidationError({"file": f"The uploaded image is invalid: {exc}"}) from exc
        elif content_type.startswith("video/"):
            self.kind = self.Kind.VIDEO
        elif content_type.startswith("audio/"):
            self.kind = self.Kind.AUDIO
        else:
            self.kind = self.Kind.FILE
            # Allow-list common document/archive/code formats; unknown files are
            # still stored as generic attachments, never rendered as HTML.
            allowed_exts = {
                ".pdf", ".txt", ".md", ".zip", ".tar", ".gz", ".bz2", ".7z", ".json", ".csv",
                ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                ".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".scss", ".html", ".xml", ".yaml", ".yml",
                ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
                ".mp4", ".webm", ".mov", ".m4v", ".mp3", ".wav", ".ogg", ".m4a",
            }
            if ext and len(ext) > 16:
                raise ValidationError({"file": "Unsupported file extension."})
            if ext and ext not in allowed_exts:
                raise ValidationError({"file": "This file type is not allowed."})

    def save(self, *args, **kwargs):
        if not self.name and self.file:
            self.name = os.path.basename(self.file.name)[:255]
        self.mime_type = (
            getattr(self.file, "content_type", "")
            or self.mime_type
            or mimetypes.guess_type(getattr(self.file, "name", "") or "")[0]
            or "application/octet-stream"
        )
        self.size_bytes = getattr(self.file, "size", 0) or self.size_bytes or 0
        self.full_clean()
        super().save(*args, **kwargs)
