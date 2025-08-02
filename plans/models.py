from django.db import models
from django.utils.translation import gettext_lazy as _
from core.global_settings import config
from uuid import uuid4
from core.base.BaseModel import BaseModel


class PlanTypeChoices(models.TextChoices):
    DB = "DB", _("DB")
    APP = "APP", _("APP")
    READY = "READY", _("READY")


class StorageTypeChoices(models.TextChoices):
    SSD = "SSD", _("SSD")
    HDD = "HDD", _("HDD")


class NameChoices(models.TextChoices):
    BRONZE = "Bronze", _("Bronze")
    SILVER = "Silver", _("Silver")
    GOLD = "Gold", _("Gold")
    Diamond = "Diamond", _("Diamond")


class Plan(BaseModel):
    name = models.CharField(_("Name"), max_length=50, choices=NameChoices.choices)
    platform = models.CharField(_("Platform"), max_length=20, choices=getattr(config, "PLATFORM_CHOICES", []))
    max_cpu = models.IntegerField(_("Maximum CPU (vCPU)"))
    max_ram = models.IntegerField(_("Maximum RAM (MB)"))
    max_storage = models.IntegerField(_("Maximum Storage (GB)"))
    price_per_hour = models.FloatField(_("Price Per Hour (Toman)"), default=0.0)
    storage_type = models.CharField(_("Storage Type"), max_length=10, choices=StorageTypeChoices.choices)
    plan_type = models.CharField(_("Plan Type"), max_length=10, choices=PlanTypeChoices.choices)

    class Meta:
        verbose_name = _("Plan")
        verbose_name_plural = _("Plans")

    def __str__(self):
        return f"{self.name}, {self.platform}"
