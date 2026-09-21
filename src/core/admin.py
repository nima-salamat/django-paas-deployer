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



# ---------------------------------------------------------------------------
# Cache dashboards (core app cache + messenger message cache)
# ---------------------------------------------------------------------------
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from django.urls import path
from django.contrib import messages as dj_messages


@staff_member_required
def app_cache_dashboard_view(request):
    from core.app_cache import (
        get_app_cache_overview,
        scan_app_cache_keys,
        invalidate_namespace,
        get_cache_key_preview,
        delete_cache_keys,
    )
    if request.method == "POST":
        action = request.POST.get("action") or ""
        if action == "flush":
            ns = request.POST.get("ns") or "all"
            invalidate_namespace(ns)
            dj_messages.success(request, f"Flushed cache namespace: {ns}")
            return redirect("core_app_cache_dashboard")
        if action == "delete_key":
            key = (request.POST.get("key") or "").strip()
            if key:
                n = delete_cache_keys(key)
                dj_messages.success(request, f"Deleted {n} key(s): {key}")
            return redirect(request.get_full_path() if request.GET else "core_app_cache_dashboard")
        if action == "preview_key":
            key = (request.POST.get("key") or "").strip()
            pattern = request.GET.get("pattern") or ""
            try:
                limit = min(500, max(1, int(request.GET.get("limit") or 80)))
            except ValueError:
                limit = 80
            keys = scan_app_cache_keys(pattern, limit) if pattern else []
            preview = get_cache_key_preview(key) if key else None
            return render(
                request,
                "admin/core/cache_dashboard.html",
                {
                    "title": "App Cache",
                    "overview": get_app_cache_overview(),
                    "pattern": pattern,
                    "limit": limit,
                    "keys": keys,
                    "preview": preview,
                },
            )

    pattern = request.GET.get("pattern") or ""
    try:
        limit = min(500, max(1, int(request.GET.get("limit") or 80)))
    except ValueError:
        limit = 80
    keys = scan_app_cache_keys(pattern, limit) if pattern else []
    preview_key = (request.GET.get("preview") or "").strip()
    preview = get_cache_key_preview(preview_key) if preview_key else None
    return render(
        request,
        "admin/core/cache_dashboard.html",
        {
            "title": "App Cache",
            "overview": get_app_cache_overview(),
            "pattern": pattern,
            "limit": limit,
            "keys": keys,
            "preview": preview,
        },
    )


def _patched_admin_get_urls():
    from django.contrib import admin as dj_admin
    # Call the real unbound method stored once
    urls = _ADMIN_GET_URLS_ORIG()
    custom = [
        path(
            "core/cache/",
            dj_admin.site.admin_view(app_cache_dashboard_view),
            name="core_app_cache_dashboard",
        ),
    ]
    try:
        from messenger.admin import cache_dashboard_view
        custom.append(
            path(
                "messenger/cache/",
                dj_admin.site.admin_view(cache_dashboard_view),
                name="messenger_cache_dashboard",
            )
        )
    except Exception:
        pass
    return custom + urls


from django.contrib import admin as _admin_mod
_ADMIN_GET_URLS_ORIG = _admin_mod.site.get_urls
_admin_mod.site.get_urls = _patched_admin_get_urls
