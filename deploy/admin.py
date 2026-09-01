from django.contrib import admin, messages
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import Deploy, DeployLog


# ─────────────────────────────────────────────────────────────
# Deploy
# ─────────────────────────────────────────────────────────────
@admin.register(Deploy)
class DeployAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "service_link",
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
        "service__user__username",
        "status_message",
        "error_message",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 25
    list_select_related = ("service", "service__user")
    autocomplete_fields = ("service",)
    actions = ["mark_cancelled"]

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
        (
            "Basic",
            {
                "fields": (
                    "name",
                    "service",
                    "version",
                    "zip_file",
                    "download_link_detail",
                ),
            },
        ),
        (
            "Configuration",
            {
                "fields": ("config",),
                "classes": ("collapse",),
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "status",
                    "stage",
                    "progress",
                    "status_message",
                    "error_message",
                    "rollback_status",
                    "cancel_requested",
                ),
            },
        ),
        (
            "Runtime Health",
            {
                "fields": (
                    "health_status",
                    "container_status",
                    "image_status",
                    "volume_status",
                    "network_status",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "started_at",
                    "completed_at",
                    "updated_file_at",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    @admin.display(description="Service", ordering="service__name")
    def service_link(self, obj):
        if not obj.service_id:
            return "—"
        url = reverse("admin:services_service_change", args=[obj.service_id])
        return format_html(
            '<a href="{}">{}</a>',
            url,
            obj.service.name,
        )

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        colors = {
            "pending": ("#6b7280", "Pending"),
            "running": ("#2563eb", "Running"),
            "succeeded": ("#16a34a", "Succeeded"),
            "failed": ("#dc2626", "Failed"),
            "rolling_back": ("#d97706", "Rolling back"),
            "rolled_back": ("#9333ea", "Rolled back"),
            "cancelled": ("#9ca3af", "Cancelled"),
        }
        color, label = colors.get(obj.status, ("#6b7280", obj.get_status_display()))
        return format_html(
            '<span class="badge" style="background:{};">{}</span>',
            color,
            label,
        )

    @admin.display(description="Progress", ordering="progress")
    def progress_bar(self, obj):
        pct = max(0, min(100, int(obj.progress or 0)))
        if pct >= 100:
            color = "#16a34a"
        elif pct > 0:
            color = "#2563eb"
        else:
            color = "#6b7280"
        return format_html(
            '<div class="progress-wrap">'
            '<div class="progress-bar-bg">'
            '<div class="progress-bar-fill" style="width:{}%;background:{};"></div>'
            "</div>"
            '<span style="font-size:11px;color:#8b949e;">{}%</span>'
            "</div>",
            pct,
            color,
            pct,
        )

    @admin.display(description="ZIP", boolean=True)
    def has_zip(self, obj):
        return bool(obj.zip_file)

    @admin.display(description="Download")
    def download_link(self, obj):
        if not obj.zip_file:
            return format_html('<span style="color:#6e7681;">—</span>')
        url = reverse("deploy-download", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" style="padding:3px 12px;font-size:12px;">'
            "⬇ Download</a>",
            url,
        )

    @admin.display(description="Download ZIP")
    def download_link_detail(self, obj):
        if not obj.zip_file:
            return format_html(
                '<span style="color:#8b949e;">No file uploaded</span>'
            )
        url = reverse("deploy-download", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" style="padding:8px 18px;font-weight:600;">'
            "⬇ Download ZIP</a>",
            url,
        )

    @admin.action(description="Request cancel on selected deployments")
    def mark_cancelled(self, request, queryset):
        updated = queryset.filter(
            status__in=["pending", "running"]
        ).update(cancel_requested=True)
        self.message_user(
            request,
            f"Cancel requested for {updated} deployment(s).",
        )


# ─────────────────────────────────────────────────────────────
# Deploy Log
# ─────────────────────────────────────────────────────────────
@admin.register(DeployLog)
class DeployLogAdmin(admin.ModelAdmin):
    list_display = (
        "deploy_identifier",
        "service_identifier",
        "stage",
        "event_type",
        "level_badge",
        "progress",
        "message_short",
        "created_at",
    )
    list_filter = ("stage", "level", "event_type", "created_at")
    search_fields = ("message", "event_type", "exception_type", "traceback")
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
        alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", "default")
        return super().get_queryset(request).using(alias)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

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
            "critical": "#7f1d1d",
        }
        color = colors.get(str(obj.level).lower(), "#6b7280")
        return format_html(
            '<span class="badge" style="background:{};">{}</span>',
            color,
            str(obj.level).upper(),
        )

    @admin.display(description="Message")
    def message_short(self, obj):
        msg = obj.message or ""
        if len(msg) > 80:
            return msg[:80] + "…"
        return msg

from .models import BaseRuntimeImage


@admin.register(BaseRuntimeImage)
class BaseRuntimeImageAdmin(admin.ModelAdmin):
    list_display = (
        "runtime_label", "variant", "status_badge", "enabled", "auto_build",
        "image_ref", "docker_host", "build_count", "build_completed_at",
    )
    list_filter = ("logical_runtime", "variant", "status", "enabled", "auto_build", "docker_host")
    search_fields = ("logical_runtime", "runtime_version", "image_ref", "source_image", "docker_host", "last_error")
    ordering = ("logical_runtime", "runtime_version", "variant")
    actions = ("rebuild_selected", "enable_selected", "disable_selected", "delete_docker_images")
    readonly_fields = (
        "image_ref", "image_id", "image_digest", "source_image", "docker_host", "status",
        "rebuild_requested", "rebuild_requested_at", "build_started_at", "build_completed_at",
        "build_count", "build_task_id", "build_owner_deployment_id", "last_error", "created_at", "updated_at",
    )

    fieldsets = (
        ("Runtime", {"fields": ("logical_runtime", "runtime_version", "variant", "architecture")}),
        ("Docker image", {"fields": ("source_image", "image_repository", "image_tag", "image_ref", "image_id", "image_digest", "docker_host")}),
        ("Policy", {"fields": ("enabled", "auto_build", "rebuild_requested")}),
        ("Build state", {"fields": ("status", "rebuild_requested_at", "build_started_at", "build_completed_at", "build_count", "build_task_id", "build_owner_deployment_id", "last_error")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Runtime", ordering="runtime_version")
    def runtime_label(self, obj):
        return f"{obj.logical_runtime} {obj.runtime_version}"

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        colors = {"pending": "#6b7280", "building": "#2563eb", "ready": "#16a34a", "failed": "#dc2626", "disabled": "#9ca3af"}
        color = colors.get(obj.status, "#6b7280")
        return format_html('<span class="badge" style="background:{};">{}</span>', color, obj.get_status_display())

    @admin.action(description="Rebuild selected base images")
    def rebuild_selected(self, request, queryset):
        from django.utils import timezone
        from deployments.celery.tasks import build_base_runtime_image
        count = 0
        for obj in queryset:
            obj.status = BaseRuntimeImage.Status.PENDING
            obj.enabled = True
            obj.rebuild_requested = True
            obj.rebuild_requested_at = timezone.now()
            obj.save(update_fields=["status", "enabled", "rebuild_requested", "rebuild_requested_at", "updated_at"])
            build_base_runtime_image.apply_async(args=[str(obj.pk)])
            count += 1
        self.message_user(request, f"Queued rebuild for {count} base image(s).")

    @admin.action(description="Enable selected base images")
    def enable_selected(self, request, queryset):
        count = queryset.update(enabled=True, status=BaseRuntimeImage.Status.PENDING)
        self.message_user(request, f"Enabled {count} base image(s).")

    @admin.action(description="Disable selected base images")
    def disable_selected(self, request, queryset):
        count = queryset.update(enabled=False, status=BaseRuntimeImage.Status.DISABLED)
        self.message_user(request, f"Disabled {count} base image(s).")

    @admin.action(description="Remove Docker image for selected rows")
    def delete_docker_images(self, request, queryset):
        from deployments.core.manager.image_manager import Image
        count = 0
        for obj in queryset:
            try:
                Image.remove_by_name(obj.image_ref)
            except Exception:
                self.message_user(request, f"Failed to remove {obj.image_ref}.", level=messages.ERROR)
                continue
            count += 1
        self.message_user(request, f"Removed Docker image for {count} row(s).")
    def delete_model(self, request, obj):
        try:
            from deployments.core.manager.image_manager import Image
            Image.remove_by_name(obj.image_ref)
        except Exception:
            self.message_user(request, f"Could not remove Docker image {obj.image_ref}; removing registry record anyway.", level=messages.WARNING)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        from deployments.core.manager.image_manager import Image
        for obj in queryset:
            try:
                Image.remove_by_name(obj.image_ref)
            except Exception:
                self.message_user(request, f"Could not remove Docker image {obj.image_ref}.", level=messages.WARNING)
        super().delete_queryset(request, queryset)

