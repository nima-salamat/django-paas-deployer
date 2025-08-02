from django.contrib import admin
from .models import Deploy

@admin.register(Deploy)
class DeployAdmin(admin.ModelAdmin):
    list_display = ("name", "service", "version", "running", "started_at")
    list_filter = ("running", "service", "started_at")
    search_fields = ("name", "service__name")
    readonly_fields = ("started_at",)
    fieldsets = (
        (None, {
            "fields": ("name", "service", "version", "zip_file", "config", "running", "started_at")
        }),
    )