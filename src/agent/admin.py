from django.contrib import admin

from core.django_admin import AuditReadOnlyAdmin, ProjectModelAdmin, SensitiveReadOnlyAdmin
from .models import (
    Agent, AgentAuditEvent, AgentCredential, AgentEnrollmentToken,
    AgentIdempotencyRecord,
)


@admin.register(Agent)
class AgentAdmin(ProjectModelAdmin):
    list_display = ("id", "name", "user", "status", "provisioning_source", "last_used_at", "created_at")
    list_filter = ("status", "provisioning_source")
    search_fields = ("name", "user__username", "user__email")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(AgentCredential)
class AgentCredentialAdmin(SensitiveReadOnlyAdmin):
    list_display = ("id", "agent", "token_prefix", "token_type", "expires_at", "revoked_at", "last_used_at")
    list_filter = ("token_type",)
    search_fields = ("token_prefix", "agent__name")
    raw_id_fields = ("agent",)


@admin.register(AgentEnrollmentToken)
class AgentEnrollmentTokenAdmin(SensitiveReadOnlyAdmin):
    list_display = ("id", "agent", "token_prefix", "expires_at", "used_at", "issued_from_ip", "created_at")
    search_fields = ("token_prefix", "agent__name")
    raw_id_fields = ("agent",)


@admin.register(AgentAuditEvent)
class AgentAuditEventAdmin(AuditReadOnlyAdmin):
    list_display = ("id", "action", "resource_type", "resource_id", "success", "http_status", "occurred_at")
    list_filter = ("success", "failure_domain", "retryability", "visibility")
    search_fields = ("action", "resource_type", "resource_id", "request_id", "error_code")
    raw_id_fields = ("agent", "user", "credential")


@admin.register(AgentIdempotencyRecord)
class AgentIdempotencyRecordAdmin(AuditReadOnlyAdmin):
    list_display = ("id", "agent", "key", "method", "path", "state", "status_code", "expires_at")
    list_filter = ("state", "method")
    search_fields = ("key", "path", "agent__name")
    raw_id_fields = ("agent",)
