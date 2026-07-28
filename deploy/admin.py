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
    list_display = ("deploy_id", "service_id", "stage", "event_type", "level", "progress", "created_at")
    list_filter = ("stage", "level", "created_at")
    search_fields = ("message", "event_type")
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
    
