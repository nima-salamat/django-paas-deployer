from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import SystemSetting


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = (
        "key",
        "category",
        "label",
        "short_value",
        "value_type",
        "is_editable",
        "is_secret",
        "updated_at",
    )
    list_filter = ("category", "value_type", "is_editable", "is_secret")
    search_fields = ("key", "label", "description", "value")
    readonly_fields = ("created_at", "updated_at", "key")
    ordering = ("category", "key")
    list_per_page = 50
    actions = ("reseed_missing_from_code",)

    fieldsets = (
        (None, {"fields": ("key", "label", "category", "description")}),
        (_("Value"), {"fields": ("value_type", "value", "is_secret", "is_editable")}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def short_value(self, obj: SystemSetting):
        if obj.is_secret:
            return format_html('<span style="color:#999">••••••</span>')
        v = obj.value or ""
        return (v[:77] + "…") if len(v) > 80 else v

    short_value.short_description = _("Value")

    def has_delete_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def get_readonly_fields(self, request, obj=None):
        ro = list(self.readonly_fields)
        if obj and not obj.is_editable and not request.user.is_superuser:
            ro = list(set(ro + ["value", "value_type", "is_editable"]))
        return ro

    @admin.action(description=_("Seed missing settings from code defaults"))
    def reseed_missing_from_code(self, request, queryset):
        from core.initial_config import (
            seed_system_settings,
            seed_dockerfile_templates_from_config,
        )

        n = seed_system_settings(update_existing=False)
        d = seed_dockerfile_templates_from_config()
        self.message_user(
            request,
            f"Seeded {n} setting(s), {d} dockerfile template(s).",
            level=messages.SUCCESS,
        )
