from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Service, PrivateNetwork, Volume


# ─────────────────────────────────────────────────────────────
# Private Network
# ─────────────────────────────────────────────────────────────
@admin.register(PrivateNetwork)
class PrivateNetworkAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "user_link",
        "description_short",
        "service_count",
        "docker_name",
        "created_at",
    )
    list_display_links = ("id", "name")
    search_fields = ("name", "description", "user__username", "user__email")
    list_filter = ("user", "created_at")
    ordering = ("-created_at",)
    list_per_page = 25
    autocomplete_fields = ("user",)
    readonly_fields = ("docker_name", "created_at", "updated_at")

    fieldsets = (
        (
            None,
            {
                "fields": ("name", "user", "description"),
            },
        ),
        (
            "Docker",
            {
                "fields": ("docker_name",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="User", ordering="user__username")
    def user_link(self, obj):
        if not obj.user_id:
            return "—"
        url = reverse("admin:users_user_change", args=[obj.user_id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)

    @admin.display(description="Description")
    def description_short(self, obj):
        if obj.description:
            text = obj.description
            return (text[:75] + "…") if len(text) > 75 else text
        return format_html('<span style="color:#6e7681;">—</span>')

    @admin.display(description="Services")
    def service_count(self, obj):
        count = obj.Service.count()
        if count == 0:
            return format_html('<span style="color:#6e7681;">0</span>')
        return format_html(
            '<span class="badge badge-primary">{}</span>',
            count,
        )

    @admin.display(description="Docker Network")
    def docker_name(self, obj):
        return format_html(
            '<code style="font-size:12px;">{}</code>',
            obj.get_docker_network_name(),
        )


# ─────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────
@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "user_link",
        "plan_link",
        "network_link",
        "selected_deploy_link",
        "status_badge",
        "read_only",
        "deployed_at",
        "created_at",
    )
    list_display_links = ("id", "name")
    search_fields = (
        "name",
        "user__username",
        "user__email",
        "plan__name",
        "network__name",
    )
    list_filter = ("plan", "network", "status", "read_only", "created_at")
    ordering = ("-created_at",)
    list_per_page = 25
    list_select_related = ("user", "plan", "network", "selected_deploy")
    autocomplete_fields = ("user", "plan", "network", "selected_deploy")
    readonly_fields = (
        "selected_deploy_at",
        "deploy_started",
        "deployed_at",
        "docker_service_name",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Identity",
            {
                "fields": ("name", "user", "plan", "network", "read_only"),
            },
        ),
        (
            "Deployment",
            {
                "fields": (
                    "selected_deploy",
                    "selected_deploy_at",
                    "deploy_started",
                    "deployed_at",
                    "status",
                    "task_id",
                ),
            },
        ),
        (
            "Docker",
            {
                "fields": ("docker_service_name",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="User", ordering="user__username")
    def user_link(self, obj):
        if not obj.user_id:
            return "—"
        url = reverse("admin:users_user_change", args=[obj.user_id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)

    @admin.display(description="Plan", ordering="plan__name")
    def plan_link(self, obj):
        if not obj.plan_id:
            return "—"
        url = reverse("admin:plans_plan_change", args=[obj.plan_id])
        return format_html('<a href="{}">{}</a>', url, obj.plan.name)

    @admin.display(description="Network", ordering="network__name")
    def network_link(self, obj):
        if not obj.network_id:
            return format_html('<span style="color:#6e7681;">—</span>')
        url = reverse("admin:services_privatenetwork_change", args=[obj.network_id])
        return format_html('<a href="{}">{}</a>', url, obj.network.name)

    @admin.display(description="Selected Deploy")
    def selected_deploy_link(self, obj):
        if not obj.selected_deploy_id:
            return format_html('<span style="color:#6e7681;">—</span>')
        url = reverse("admin:deploy_deploy_change", args=[obj.selected_deploy_id])
        return format_html(
            '<a href="{}">{}</a>',
            url,
            obj.selected_deploy.name,
        )

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        # Adjust keys to match your SERVICE_STATUS_CHOICES values
        colors = {
            "stopped": "#6b7280",
            "running": "#16a34a",
            "deploying": "#2563eb",
            "failed": "#dc2626",
            "pending": "#f59e0b",
            "error": "#dc2626",
        }
        color = colors.get(str(obj.status).lower(), "#6b7280")
        label = obj.get_status_display() if hasattr(obj, "get_status_display") else obj.status
        return format_html(
            '<span class="badge" style="background:{};">{}</span>',
            color,
            label,
        )

    @admin.display(description="Docker Service")
    def docker_service_name(self, obj):
        return format_html(
            '<code style="font-size:12px;">{}</code>',
            obj.get_docker_service_name(),
        )


# ─────────────────────────────────────────────────────────────
# Volume
# ─────────────────────────────────────────────────────────────
@admin.register(Volume)
class VolumeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "user_link",
        "legacy_service_link",
        "default_bind",
        "default_mode",
        "size_mb_display",
        "attachment_count",
        "docker_volume_name",
        "created_at",
    )
    list_display_links = ("id", "name")
    search_fields = (
        "name",
        "user__username",
        "user__email",
        "service__name",
        "default_bind",
    )
    list_filter = ("default_mode", "user", "created_at")
    ordering = ("-created_at",)
    list_per_page = 25
    autocomplete_fields = ("user", "service")
    readonly_fields = (
        "service_attachments_pretty",
        "docker_volume_name",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Identity",
            {
                "fields": ("name", "user", "size_mb"),
            },
        ),
        (
            "Defaults",
            {
                "fields": ("default_bind", "default_mode"),
            },
        ),
        (
            "Attachments",
            {
                "fields": (
                    "service",
                    "service_attachments",
                    "service_attachments_pretty",
                ),
            },
        ),
        (
            "Docker",
            {
                "fields": ("docker_volume_name",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="User", ordering="user__username")
    def user_link(self, obj):
        if not obj.user_id:
            return "—"
        url = reverse("admin:users_user_change", args=[obj.user_id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)

    @admin.display(description="Legacy Service")
    def legacy_service_link(self, obj):
        if not obj.service_id:
            return format_html('<span style="color:#6e7681;">—</span>')
        url = reverse("admin:services_service_change", args=[obj.service_id])
        return format_html('<a href="{}">{}</a>', url, obj.service.name)

    @admin.display(description="Size", ordering="size_mb")
    def size_mb_display(self, obj):
        return f"{obj.size_mb:,} MB"

    @admin.display(description="Attachments")
    def attachment_count(self, obj):
        attachments = obj.service_attachments or {}
        count = len(attachments)
        if count == 0:
            return format_html('<span style="color:#6e7681;">0</span>')
        return format_html(
            '<span class="badge badge-info">{}</span>',
            count,
        )

    @admin.display(description="Docker Volume")
    def docker_volume_name(self, obj):
        return format_html(
            '<code style="font-size:12px;">{}</code>',
            obj.get_docker_volume_name(),
        )

    @admin.display(description="Attachments (pretty)")
    def service_attachments_pretty(self, obj):
        import json
        data = obj.service_attachments or {}
        if not data:
            return "—"
        pretty = json.dumps(data, indent=2, ensure_ascii=False)
        return format_html(
            '<pre style="background:#0f1117;padding:12px;border-radius:6px;'
            'font-size:12px;max-height:300px;overflow:auto;">{}</pre>',
            pretty,
        )


from .models import ShellSession

@admin.register(ShellSession)
class ShellSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "service", "user", "platform", "status", "workdir", "expires_at", "last_used_at")
    list_filter = ("status", "platform")
    search_fields = ("service__name", "user__email", "user__username")
    readonly_fields = ("token_hash", "created_at", "updated_at", "last_used_at", "expires_at", "closed_at")
