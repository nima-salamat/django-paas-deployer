from django.db import models
from django.core.exceptions import ValidationError
from config.BaseModel import BaseModel
from services.models import Service
from django.utils.translation import gettext_lazy as _

def zip_file_path(obj, filename):
    return f'deployments/{obj.name}/{filename}'

class Deploy(BaseModel):
    name = models.CharField(verbose_name=_("Name"), max_length=50, unique=True)
    service = models.ForeignKey(Service, verbose_name=_("Service"), on_delete=models.CASCADE)
    version = models.FloatField(verbose_name=_("Version"), default=0.00)
    zip_file = models.FileField(verbose_name=_("ZIP File"), upload_to=zip_file_path, blank=True, null=True)
    config = models.JSONField(verbose_name=_("Configuration"), blank=True, null=True)
    running = models.BooleanField(verbose_name=_("Running"), default=False)
    started_at = models.DateTimeField(verbose_name=_("Start Time"), blank=True, null=True)

    MAX_ZIP_SIZE_MB = 10

    def clean(self):
        super().clean()
        if self.zip_file:
            if self.zip_file.size > self.MAX_ZIP_SIZE_MB * 1024 * 1024:
                raise ValidationError(
                    {"zip_file": _(f"ZIP file size must be under {self.MAX_ZIP_SIZE_MB} MB.")}
                )

    def __str__(self):
        return f"{self.name} (v{self.version})"
