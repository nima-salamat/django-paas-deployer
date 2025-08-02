from django.db import models
from django.utils.translation import gettext_lazy as _
from core.global_settings import config
from core.base.BaseModel import BaseModel


class PlanTypeChoices(models.TextChoices):
    DB = "DB", _("Database")
    APP = "APP", _("Application")
    READY = "READY", _("Ready-made")


class StorageTypeChoices(models.TextChoices):
    SSD = "SSD", _("SSD")
    HDD = "HDD", _("HDD")


class NameChoices(models.TextChoices):
    BRONZE = "Bronze", _("Bronze")
    SILVER = "Silver", _("Silver")
    GOLD = "Gold", _("Gold")
    DIAMOND = "Diamond", _("Diamond")


class Plan(BaseModel):
    name = models.CharField(
        _("Name"),
        max_length=50,
        choices=NameChoices.choices,
        help_text=_("Plan level name (e.g. Bronze, Silver, etc.)")
    )
    platform = models.CharField(
        _("Platform"),
        max_length=20,
        choices=getattr(config, "PLATFORM_CHOICES", []),
        help_text=_("Technology platform this plan supports")
    )
    max_cpu = models.IntegerField(_("Maximum CPU (vCPU)"))
    max_ram = models.IntegerField(_("Maximum RAM (MB)"))
    max_storage = models.IntegerField(_("Maximum Storage (GB)"))
    price_per_hour = models.FloatField(
        _("Price Per Hour (Toman)"),
        default=0.0,
        help_text=_("Hourly pricing in Toman")
    )
    storage_type = models.CharField(
        _("Storage Type"),
        max_length=10,
        choices=StorageTypeChoices.choices
    )
    plan_type = models.CharField(
        _("Plan Type"),
        max_length=10,
        choices=PlanTypeChoices.choices
    )

    class Meta:
        verbose_name = _("Plan")
        verbose_name_plural = _("Plans")

    def __str__(self):
        return f"{self.name} - {self.platform}"

    def __repr__(self):
        return f"<Plan {self.name} ({self.platform})>"

    @property
    def price_per_day(self):
        return round(self.price_per_hour * 24, 2)

    @property
    def price_per_month(self):
        return round(self.price_per_hour * 24 * 30, 2)

    def clean(self):
        if self.max_cpu < 1:
            raise ValueError(_("CPU count must be at least 1"))
        if self.max_ram < 256:
            raise ValueError(_("RAM must be at least 256 MB"))
        if self.max_storage < 1:
            raise ValueError(_("Storage must be at least 1 GB"))
        if self.price_per_hour < 0:
            raise ValueError(_("Price per hour cannot be negative"))
