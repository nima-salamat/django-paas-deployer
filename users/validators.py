from django.core.files.images import get_image_dimensions
from django.utils.deconstruct import deconstructible
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _



@deconstructible
class ImageValidator:
    def __init__(self, size_kb, max_w, max_h):
        self.size_kb = size_kb
        self.max_w = max_w
        self.max_h = max_h

    def __call__(self, pic):
        w, h = get_image_dimensions(pic)
        size_kb = pic.size // 1024
        if w <= self.max_w and h <= self.max_h and size_kb <= self.size_kb:
            return
        raise ValidationError(
            _(f"Image file size must be ≤ {self.size_kb} KB and dimensions ≤ {self.max_w}×{self.max_h}px.")
        )