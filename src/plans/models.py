from django.db import models
from django.utils.translation import gettext_lazy as _
from core.global_settings.config import NameChoices, PlanTypeChoices, PLATFORM_CHOICES, StorageTypeChoices
from core.base.BaseModel import BaseModel


class Plan(BaseModel):
    name = models.CharField(
        _("Name"),
        max_length=50,
        choices=NameChoices.choices,
        default=NameChoices.BRONZE,
        help_text=_("Plan level name (e.g. Bronze, Silver, etc.)")
    )
    platform = models.CharField(
        _("Platform"),
        max_length=20,
        choices=PLATFORM_CHOICES,
        help_text=_("Technology platform this plan supports")
    )
    max_cpu = models.FloatField(_("Maximum CPU (vCPU)"))
    max_ram = models.FloatField(_("Maximum RAM (MB)"))
    max_storage = models.PositiveIntegerField(_("Maximum Storage (GB)"))
    price_per_hour = models.FloatField(
        _("Price Per Hour (Toman)"),
        default=0.0,
        help_text=_("Hourly pricing in Toman")
    )
    storage_type = models.CharField(
        _("Storage Type"),
        max_length=10,
        choices=StorageTypeChoices.choices,
        default=StorageTypeChoices.HDD
    )
    plan_type = models.CharField(
        _("Plan Type"),
        max_length=10,
        choices=PlanTypeChoices.choices,
        default= PlanTypeChoices.APP
    )
    # Runtime logging commercial limits (independent from max_storage app disk)
    log_retention_days = models.PositiveIntegerField(
        _("Log retention (days)"), null=True, blank=True,
        help_text=_("Null inherits platform default."),
    )
    log_storage_mb = models.PositiveIntegerField(
        _("Log storage quota (MB)"), null=True, blank=True,
        help_text=_("Per-service persistent log storage. Null inherits platform default."),
    )
    log_ingest_bytes_per_sec = models.PositiveIntegerField(
        _("Log ingest limit (bytes/sec)"), null=True, blank=True,
    )
    persistent_logging = models.BooleanField(
        _("Persistent logging"), null=True, blank=True,
        help_text=_("Null inherits platform default."),
    )
    realtime_logging = models.BooleanField(
        _("Realtime logging"), null=True, blank=True,
    )
    log_quota_behavior = models.CharField(
        _("Log quota behavior"), max_length=32, blank=True, default="",
        help_text=_("fifo_delete | drop_new | realtime_only; blank inherits platform."),
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
