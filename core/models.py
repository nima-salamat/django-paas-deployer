"""
Persistent system configuration (replaces hard-coded core.global_settings.config values).

Keys are stable strings; values are stored as text and cast via value_type.
"""
from __future__ import annotations

from django.core.cache import cache
from django.db import models
from django.utils.translation import gettext_lazy as _


class SettingValueType(models.TextChoices):
    STRING = "string", _("String")
    INTEGER = "integer", _("Integer")
    FLOAT = "float", _("Float")
    BOOLEAN = "boolean", _("Boolean")
    JSON = "json", _("JSON")


class SettingCategory(models.TextChoices):
    MIRRORS = "mirrors", _("Registry / package mirrors")
    RUNTIME = "runtime", _("Default runtime versions")
    PORTS = "ports", _("Default ports")
    BUILD = "build", _("Docker image build limits")
    DEPLOY = "deploy", _("Deployment behaviour")
    DOCKERFILE = "dockerfile", _("Dockerfile templates")
    GENERAL = "general", _("General")


class SystemSetting(models.Model):
    key = models.CharField(
        _("Key"),
        max_length=128,
        unique=True,
        db_index=True,
        help_text=_("Stable machine key, e.g. mirror.python or build.max_cpu"),
    )
    value = models.TextField(
        _("Value"),
        blank=True,
        default="",
        help_text=_("Stored as text; cast using value_type."),
    )
    value_type = models.CharField(
        _("Value type"),
        max_length=16,
        choices=SettingValueType.choices,
        default=SettingValueType.STRING,
    )
    category = models.CharField(
        _("Category"),
        max_length=32,
        choices=SettingCategory.choices,
        default=SettingCategory.GENERAL,
        db_index=True,
    )
    label = models.CharField(_("Label"), max_length=128, blank=True, default="")
    description = models.TextField(_("Description"), blank=True, default="")
    is_secret = models.BooleanField(
        _("Secret"),
        default=False,
        help_text=_("Hide raw value in non-staff API responses."),
    )
    is_editable = models.BooleanField(
        _("Editable"),
        default=True,
        help_text=_("If false, admin/API cannot change this key."),
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("System setting")
        verbose_name_plural = _("System settings")
        ordering = ("category", "key")

    def __str__(self) -> str:
        return f"{self.key}={self.value[:40]}"

    def cast_value(self):
        import json

        raw = self.value
        t = self.value_type
        if t == SettingValueType.INTEGER:
            try:
                return int(raw)
            except (TypeError, ValueError):
                return 0
        if t == SettingValueType.FLOAT:
            try:
                return float(raw)
            except (TypeError, ValueError):
                return 0.0
        if t == SettingValueType.BOOLEAN:
            return str(raw).strip().lower() in ("1", "true", "yes", "on")
        if t == SettingValueType.JSON:
            try:
                return json.loads(raw) if raw else None
            except Exception:
                return None
        return raw

    def set_cast_value(self, value) -> None:
        import json

        t = self.value_type
        if t == SettingValueType.JSON:
            self.value = json.dumps(value, ensure_ascii=False)
        elif t == SettingValueType.BOOLEAN:
            self.value = "true" if bool(value) else "false"
        else:
            self.value = "" if value is None else str(value)


# Cache invalidation on save/delete
_CACHE_PREFIX = "syssetting:"
_CACHE_ALL = "syssetting:__all__"


def _bust_cache(key: str | None = None) -> None:
    if key:
        cache.delete(f"{_CACHE_PREFIX}{key}")
    cache.delete(_CACHE_ALL)


from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_save, sender=SystemSetting)
def _setting_saved(sender, instance, **kwargs):
    _bust_cache(instance.key)


@receiver(post_delete, sender=SystemSetting)
def _setting_deleted(sender, instance, **kwargs):
    _bust_cache(instance.key)


# ---------------------------------------------------------------------------
# Wagtail-managed platform / deployment settings
# ---------------------------------------------------------------------------
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.contrib.settings.models import BaseGenericSetting, register_setting


@register_setting(icon="cog")
class CoreSettings(BaseGenericSetting):
    """Site-independent operator settings exposed in Wagtail's Settings menu.

    These replace deployment-sensitive toggles being hidden in code or spread
    across unrelated admin screens. Defaults are deliberately conservative:
    base-image caching is enabled, while destructive post-deploy cleanup is off.
    """

    base_images_enabled = models.BooleanField(
        default=True,
        verbose_name=_("Use base runtime image cache"),
        help_text=_("Reuse registered PHP, Python, Node and other runtime base images during deployment."),
    )
    base_images_auto_build = models.BooleanField(
        default=True,
        verbose_name=_("Auto-build missing base images"),
        help_text=_("Build a requested runtime base image automatically when it is not available on the Docker host."),
    )
    base_images_retain_after_deploy = models.BooleanField(
        default=True,
        verbose_name=_("Keep base images after deployment"),
        help_text=_("When disabled, an unused base image is removed after the deployment releases its lease. Shared images are kept until no active deployment uses them."),
    )
    base_images_auto_register_existing = models.BooleanField(
        default=True,
        verbose_name=_("Register existing Docker images"),
        help_text=_("Adopt matching runtime images already present on the Docker host instead of rebuilding them."),
    )

    mirror_docker = models.CharField(default="docker.arvancloud.ir", max_length=255, verbose_name=_("Docker registry mirror"))
    mirror_python = models.CharField(default="https://mirror-pypi.runflare.com/simple", max_length=500, verbose_name=_("PyPI mirror"))
    mirror_npm = models.CharField(default="https://package-mirror.liara.ir/repository/npm/", max_length=500, verbose_name=_("npm registry"))
    mirror_composer = models.CharField(default="https://package-mirror.liara.ir/repository/composer/", max_length=500, verbose_name=_("Composer mirror"))
    mirror_apt = models.CharField(default="http://repo.iut.ac.ir/debian/", max_length=500, verbose_name=_("APT/Debian mirror"))
    mirror_go = models.CharField(default="", max_length=500, blank=True, verbose_name=_("Go module proxy"))

    build_resource_mode = models.CharField(default="static", max_length=16, choices=(("static", "Static"), ("plan", "Plan capped")), verbose_name=_("Build resource mode"))
    build_pids_limit = models.PositiveIntegerField(default=2048, verbose_name=_("Build PID limit"))
    build_shm_mb = models.PositiveIntegerField(default=64, verbose_name=_("Build shared memory (MB)"))

    build_parallelism = models.PositiveSmallIntegerField(
        default=1,
        verbose_name=_("Maximum concurrent Docker builds"),
        help_text=_("Global build concurrency across workers."),
    )
    build_wait_minutes = models.PositiveSmallIntegerField(
        default=5, verbose_name=_("Build slot wait timeout (minutes)"),
        help_text=_("Maximum time a deployment waits for a Docker build slot."),
    )
    build_max_cpu = models.FloatField(
        default=1.0, verbose_name=_("Maximum build CPU"),
        help_text=_("Operator-only Docker build CPU ceiling."),
    )
    build_max_ram_mb = models.PositiveIntegerField(
        default=1024, verbose_name=_("Maximum build RAM (MB)"),
        help_text=_("Operator-only Docker build memory ceiling."),
    )
    build_slot_lease_seconds = models.PositiveIntegerField(
        default=900, verbose_name=_("Build slot lease (seconds)"),
        help_text=_("Lease duration used to recover abandoned build slots."),
    )
    deploy_timeout_minutes = models.PositiveIntegerField(
        default=10, verbose_name=_("Deployment timeout (minutes)"),
        help_text=_("Maximum time for an active deployment pipeline."),
    )
    queued_timeout_minutes = models.PositiveIntegerField(
        default=10, verbose_name=_("Queued/deploying timeout (minutes)"),
        help_text=_("Maximum time a service may remain queued or deploying."),
    )
    stop_timeout_minutes = models.PositiveIntegerField(
        default=5, verbose_name=_("Stop timeout (minutes)"),
        help_text=_("Maximum time allowed for an intentional service stop."),
    )
    unexpected_death_grace_seconds = models.PositiveIntegerField(
        default=15, verbose_name=_("Unexpected container death grace (seconds)"),
    )
    monitor_enabled = models.BooleanField(
        default=True, verbose_name=_("Enable deployment monitor"),
        help_text=_("Run automatic reconciliation and recovery."),
    )
    monitor_interval_seconds = models.PositiveIntegerField(
        default=30, verbose_name=_("Monitor interval (seconds)"),
        help_text=_("Actual monitor cadence. Celery Beat provides a lightweight pulse."),
    )
    monitor_batch_size = models.PositiveIntegerField(
        default=100, verbose_name=_("Monitor batch size"),
        help_text=_("Maximum deployments/services inspected per monitor tick."),
    )
    monitor_recovery_enabled = models.BooleanField(
        default=True, verbose_name=_("Enable automatic recovery"),
    )
    monitor_max_recovery_attempts = models.PositiveSmallIntegerField(
        default=3, verbose_name=_("Maximum recovery attempts"),
    )
    monitor_stale_base_build_minutes = models.PositiveIntegerField(
        default=30, verbose_name=_("Stale base build timeout (minutes)"),
    )
    monitor_stale_worker_seconds = models.PositiveIntegerField(
        default=90, verbose_name=_("Stale worker heartbeat (seconds)"),
    )
    monitor_scheduler_lock_seconds = models.PositiveIntegerField(
        default=20, verbose_name=_("Monitor scheduler lock (seconds)"),
    )
    panels = [
        MultiFieldPanel(
            [
                FieldPanel("base_images_enabled"),
                FieldPanel("base_images_auto_build"),
                FieldPanel("base_images_auto_register_existing"),
                FieldPanel("base_images_retain_after_deploy"),
            ],
            heading=_("Base runtime images"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("mirror_docker"),
                FieldPanel("mirror_python"),
                FieldPanel("mirror_npm"),
                FieldPanel("mirror_composer"),
                FieldPanel("mirror_apt"),
                FieldPanel("mirror_go"),
            ],
            heading=_("Package & registry mirrors"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("build_parallelism"),
                FieldPanel("build_resource_mode"),
                FieldPanel("build_pids_limit"),
                FieldPanel("build_shm_mb"),
                FieldPanel("build_wait_minutes"),
                FieldPanel("build_max_cpu"),
                FieldPanel("build_max_ram_mb"),
                FieldPanel("build_slot_lease_seconds"),
            ],
            heading=_("Docker build resources"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("deploy_timeout_minutes"),
                FieldPanel("queued_timeout_minutes"),
                FieldPanel("stop_timeout_minutes"),
                FieldPanel("unexpected_death_grace_seconds"),
            ],
            heading=_("Deployment timeouts"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("monitor_enabled"),
                FieldPanel("monitor_interval_seconds"),
                FieldPanel("monitor_batch_size"),
                FieldPanel("monitor_recovery_enabled"),
                FieldPanel("monitor_max_recovery_attempts"),
                FieldPanel("monitor_stale_base_build_minutes"),
                FieldPanel("monitor_stale_worker_seconds"),
                FieldPanel("monitor_scheduler_lock_seconds"),
            ],
            heading=_("Scheduler & monitor")
        ),
    ]

    class Meta:
        verbose_name = _("Core / Deployment settings")
        verbose_name_plural = _("Core / Deployment settings")
