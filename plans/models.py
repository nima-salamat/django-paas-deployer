from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from uuid import uuid4
from config.BaseModel import BaseModel

class Plan(BaseModel):
    name = models.CharField(_("Name"), max_length=50)
    platform = models.CharField(_("Platform"), max_length=20, choices=getattr(settings, "TECH_STACK_CHOICES", []))
    max_cpu = models.IntegerField(_("Maximum CPU (vCPU)"))
    max_ram = models.IntegerField(_("Maximum RAM (MB)"))
    max_storage = models.IntegerField(_("Maximum Storage (GB)"))
    price = models.DecimalField(
        _("Price"),
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text=_("Toman")
    )

    class Meta:
        verbose_name = _("Plan")
        verbose_name_plural = _("Plans")

    def __str__(self):
        return self.name

