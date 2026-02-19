from django.contrib import admin
from .models import Deploy

@admin.register(Deploy)
class DeployAdmin(admin.ModelAdmin):
    list_display = ("name", "service", "version", "started_at")
    list_filter = ("service", "started_at")
    search_fields = ("name", "service__name")
    readonly_fields = ("started_at",)
    