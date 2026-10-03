from django.contrib import admin

from core.django_admin import ProjectModelAdmin, ReadOnlyProjectModelAdmin, SensitiveReadOnlyAdmin
from .models import ApplicationInstance, ApplicationInstanceService


@admin.register(ApplicationInstance)
class ApplicationInstanceAdmin(SensitiveReadOnlyAdmin):
    list_display = ("id", "name", "catalog_id", "software_version", "variant_id", "status", "stage", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug", "catalog_id", "software_version", "variant_id", "error_code")
    raw_id_fields = ("user", "network")


@admin.register(ApplicationInstanceService)
class ApplicationInstanceServiceAdmin(ReadOnlyProjectModelAdmin):
    list_display = ("id", "instance", "service", "deploy", "service_key", "sequence", "dispatched_at")
    list_filter = ("sequence",)
    search_fields = ("service_key",)
    raw_id_fields = ("instance", "service", "deploy")
