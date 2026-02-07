from django.contrib import admin
from .models import Service, PrivateNetwork


@admin.register(PrivateNetwork)
class PrivateNetworkAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "description_short", "Service_count")
    list_display_links = ("id", "name")
    search_fields = ("name", "description", "user__username", "user__email")
    list_filter = ("user",)
    ordering = ("id",)
    list_per_page = 25

    def description_short(self, obj):
        if obj.description:
            return (obj.description[:75] + "...") if len(obj.description) > 75 else obj.description
        return "-"
    description_short.short_description = "Description"

    def Service_count(self, obj):
        return obj.Service.count()
    Service_count.short_description = "Number of Service"


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "plan", "network")
    list_display_links = ("id", "name")
    search_fields = ("name", "user__username", "user__email", "plan__name", "network__name")
    list_filter = ("plan", "network")
    ordering = ("id",)
    list_per_page = 25
