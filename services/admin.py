from django.contrib import admin
from .models import Container, PrivateNetwork


@admin.register(PrivateNetwork)
class PrivateNetworkAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "description_short", "Container_count")
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

    def Container_count(self, obj):
        return obj.Container.count()
    Container_count.short_description = "Number of Container"


@admin.register(Container)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "plan", "network")
    list_display_links = ("id", "name")
    search_fields = ("name", "user__username", "user__email", "plan__name", "network__name")
    list_filter = ("plan", "network")
    ordering = ("id",)
    list_per_page = 25
