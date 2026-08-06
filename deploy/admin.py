from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import Deploy, DeployLog


@admin.register(Deploy)
class DeployAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "service",
        "version",
        "status_badge",
        "stage",
        "progress_bar",
        "has_zip",
        "download_link",
        "started_at",
        "completed_at",
        "created_at",
    )
    list_filter = (
        "status",
        "rollback_status",
        "stage",
        "service",
        "started_at",
        "created_at",
    )
    search_fields = (
        "name",
        "service__name",
        "status_message",
        "error_message",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 25
    list_select_related = ("service", "service__user")

    readonly_fields = (
        "started_at",
        "completed_at",
        "updated_file_at",
        "status",
        "stage",
        "progress",
        "status_message",
        "error_message",
        "rollback_status",
        "health_status",
        "container_status",
        "image_status",
        "volume_status",
        "network_status",
        "cancel_requested",
        "download_link_detail",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Basic", {
            "fields": ("name", "service", "version", "zip_file", "download_link_detail"),
        }),
        ("Configuration", {
            "fields": ("config",),
            "classes": ("collapse",),
        }),
        ("Status", {
            "fields": (
                "status",
                "stage",
                "progress",
                "status_message",
                "error_message",
                "rollback_status",
                "cancel_requested",
            ),
        }),
        ("Runtime Health", {
            "fields": (
                "health_status",
                "container_status",
                "image_status",
                "volume_status",
                "network_status",
            ),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": (
                "started_at",
                "completed_at",
                "updated_file_at",
                "created_at",
                "updated_at",
            ),
        }),
    )

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        colors = {
            "pending": "#6b7280",
            "running": "#2563eb",
            "succeeded": "#16a34a",
            "failed": "#dc2626",
            "rolling_back": "#d97706",
            "rolled_back": "#9333ea",
            "cancelled": "#9ca3af",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:9999px;font-size:11px;font-weight:600;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Progress", ordering="progress")
    def progress_bar(self, obj):
        pct = max(0, min(100, int(obj.progress or 0)))
        color = "#16a34a" if pct >= 100 else "#2563eb" if pct > 0 else "#9ca3af"
        return format_html(
            '<div style="width:90px;background:#e5e7eb;border-radius:4px;'
            'overflow:hidden;height:8px;">'
            '<div style="width:{}%;background:{};height:100%;"></div></div>'
            '<span style="font-size:11px;margin-left:4px;">{}%</span>',
            pct, color, pct,
        )

    @admin.display(description="ZIP", boolean=True)
    def has_zip(self, obj):
        return bool(obj.zip_file)

    @admin.display(description="Download")
    def download_link(self, obj):
        if not obj.zip_file:
            return "—"
        url = reverse("deploy-download", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" style="padding:2px 10px;'
            'background:#2563eb;color:#fff;border-radius:4px;'
            'text-decoration:none;font-size:12px;">Download</a>',
            url,
        )

    @admin.display(description="Download ZIP")
    def download_link_detail(self, obj):
        if not obj.zip_file:
            return "No file uploaded"
        url = reverse("deploy-download", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" style="padding:6px 14px;'
            'background:#2563eb;color:#fff;border-radius:6px;'
            'text-decoration:none;font-weight:600;">⬇ Download ZIP</a>',
            url,
        )


@admin.register(DeployLog)
class DeployLogAdmin(admin.ModelAdmin):
    list_display = (
        "deploy_identifier",
        "service_identifier",
        "stage",
        "event_type",
        "level_badge",
        "progress",
        "created_at",
    )
    list_filter = ("stage", "level", "event_type", "created_at")
    search_fields = ("message", "event_type", "exception_type")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50

    fields = (
        "deploy_identifier",
        "service_identifier",
        "stage",
        "event_type",
        "level",
        "message",
        "progress",
        "details",
        "exception_type",
        "traceback",
        "created_at",
        "updated_at",
    )
    readonly_fields = fields

    def get_queryset(self, request):
        from django.conf import settings
        return super().get_queryset(request).using(settings.DEPLOYMENT_LOG_DB_ALIAS)

    @admin.display(description="Deploy")
    def deploy_identifier(self, obj):
        return obj.deploy_id

    @admin.display(description="Service")
    def service_identifier(self, obj):
        return obj.service_id

    @admin.display(description="Level", ordering="level")
    def level_badge(self, obj):
        colors = {
            "info": "#2563eb",
            "warning": "#d97706",
            "error": "#dc2626",
            "debug": "#6b7280",
        }
        color = colors.get(str(obj.level).lower(), "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:1px 7px;'
            'border-radius:9999px;font-size:11px;font-weight:600;">{}</span>',
            color,
            str(obj.level).upper(),
        )