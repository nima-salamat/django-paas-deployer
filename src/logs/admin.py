from django.contrib import admin

from core.django_admin import AuditReadOnlyAdmin
from .models import (
    CollectorHeartbeat, LogUsageDaily, ServiceLogEntry, ServiceLogStream, ServiceLogUsage,
)


@admin.register(ServiceLogStream)
class ServiceLogStreamAdmin(AuditReadOnlyAdmin):
    list_display = ("id", "service_id", "deploy_id", "container_name", "status", "started_at", "ended_at", "owner_id")
    list_filter = ("status",)
    search_fields = ("container_id", "container_name", "owner_id")
    readonly_fields = tuple(field.name for field in ServiceLogStream._meta.concrete_fields)


@admin.register(ServiceLogEntry)
class ServiceLogEntryAdmin(AuditReadOnlyAdmin):
    list_display = ("id", "service_id", "deploy_id", "stream_id", "ts", "stream", "level", "seq")
    list_filter = ("stream", "level", "truncated")
    search_fields = ("message", "fingerprint")
    readonly_fields = tuple(field.name for field in ServiceLogEntry._meta.concrete_fields)


@admin.register(ServiceLogUsage)
class ServiceLogUsageAdmin(AuditReadOnlyAdmin):
    list_display = ("service_id", "current_storage_bytes", "entry_count", "entries_dropped", "updated_at")


@admin.register(LogUsageDaily)
class LogUsageDailyAdmin(AuditReadOnlyAdmin):
    list_display = ("id", "service_id", "date", "bytes_ingested", "entries_ingested", "bytes_deleted", "entries_deleted")


@admin.register(CollectorHeartbeat)
class CollectorHeartbeatAdmin(AuditReadOnlyAdmin):
    list_display = ("id", "instance_id", "status", "last_heartbeat", "active_streams", "active_containers", "db_ok", "redis_ok")
    list_filter = ("status", "db_ok", "redis_ok")
    search_fields = ("instance_id", "status", "last_error")
