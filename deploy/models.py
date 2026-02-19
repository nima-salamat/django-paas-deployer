from django.db import models
from django.core.exceptions import ValidationError
from core.base.BaseModel import BaseModel
from services.models import Service
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


def zip_file_path(instance, filename):
    return f'deployments/{instance.name}/{filename}'



class Deploy(BaseModel):
    name = models.CharField(verbose_name=_("Name"), max_length=50, unique=True)
    service = models.ForeignKey(Service, verbose_name=_("Service"), on_delete=models.CASCADE)
    version = models.DecimalField(_("Version"), max_digits=5, decimal_places=2, default=0.00, help_text=_("Deployment version, e.g., 1.0"))
    zip_file = models.FileField(verbose_name=_("ZIP File"), upload_to=zip_file_path, blank=True, null=True)
    config = models.JSONField(verbose_name=_("Configuration"), blank=True, null=True)
    started_at = models.DateTimeField(verbose_name=_("Start Time"), blank=True, null=True, editable=False)
    updated_file_at = models.DateTimeField(blank=True, null=True)
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
        
        file_changed = False
        if self.pk and Deploy.objects.filter(pk=self.pk).exists():
            old = Deploy.objects.get(pk=self.pk)
            if old.zip_file != self.zip_file:
                file_changed = True
        else:
            file_changed = bool(self.zip_file)

        if file_changed:
            self.updated_file_at = timezone.now()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} (v{self.version})"

