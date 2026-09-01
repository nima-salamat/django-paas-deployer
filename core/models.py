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
    ]

    class Meta:
        verbose_name = _("Core / Deployment settings")
        verbose_name_plural = _("Core / Deployment settings")
