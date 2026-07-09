from django.contrib import admin
from .models import Deploy, DeployLog

@admin.register(Deploy)
class DeployAdmin(admin.ModelAdmin):
    list_display = ("name", "service", "version", "status", "stage", "progress", "started_at", "completed_at")
    list_filter = ("service", "status", "rollback_status", "started_at")
    search_fields = ("name", "service__name")
    readonly_fields = (
        "started_at",
        "completed_at",
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
    )


@admin.register(DeployLog)
class DeployLogAdmin(admin.ModelAdmin):
    list_display = ("deploy", "service", "stage", "level", "progress", "created_at")
    list_filter = ("stage", "level", "created_at")
    search_fields = ("deploy__name", "service__name", "message")
    readonly_fields = ("deploy", "service", "stage", "level", "message", "progress", "details", "created_at", "updated_at")
    
