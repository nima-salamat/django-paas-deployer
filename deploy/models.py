from django.db import models
from django.core.exceptions import ValidationError
from core.base.BaseModel import BaseModel
from services.models import Container
from django.utils.translation import gettext_lazy as _
import os

def zip_file_path(instance, filename):
    return f'deployments/{instance.name}/{filename}'

class Deploy(BaseModel):
    name = models.CharField(verbose_name=_("Name"), max_length=50, unique=True)
    service = models.ForeignKey(Container, verbose_name=_("Service"), on_delete=models.CASCADE)
    version = models.DecimalField(_("Version"), max_digits=5, decimal_places=2, default=0.00, help_text=_("Deployment version, e.g., 1.0"))
    zip_file = models.FileField(verbose_name=_("ZIP File"), upload_to=zip_file_path, blank=True, null=True)
    config = models.JSONField(verbose_name=_("Configuration"), blank=True, null=True)
    running = models.BooleanField(verbose_name=_("Running"), default=False)
    started_at = models.DateTimeField(verbose_name=_("Start Time"), blank=True, null=True, editable=False)

    MAX_ZIP_SIZE_MB = 10

    class Meta:
        verbose_name = _("Deployment")
        verbose_name_plural = _("Deployments")
    
    def clean(self):
        super().clean()
        if self.zip_file and self.zip_file.size > self.MAX_ZIP_SIZE_MB * 1024 * 1024:
            raise ValidationError({
                "zip_file": _(f"ZIP file size must be under {self.MAX_ZIP_SIZE_MB} MB.")
            })
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} (v{self.version})"

