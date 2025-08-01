from django.contrib import admin
from .models import Plan, PrivateNetwork


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "max_apps",
        "max_cpu",
        "max_ram",
        "max_storage",
        "created_at",
        "updated_at",
    )
    list_display_links = ("id", "name")
    search_fields = ("name",)
    ordering = ("name",)
    list_filter = ("max_cpu", "max_ram", "max_storage")
    list_per_page = 25

    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {
            "fields": (
                "name",
                "max_apps",
                "max_cpu",
                "max_ram",
                "max_storage",
            )
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(PrivateNetwork)
class PrivateNetworkAdmin(admin.ModelAdmin):
    list_display = ("id", "enabled", "short_description", "plans_count")
    list_display_links = ("id", "short_description")
    search_fields = ("description",)
    list_filter = ("enabled",)
    filter_horizontal = ("plans",)
    ordering = ("-enabled", "id")
    list_per_page = 25

    fieldsets = (
        (None, {
            "fields": (
                "enabled",
                "plans",
                "description",
            )
        }),
    )

    def short_description(self, obj):
        if obj.description:
            return (obj.description[:75] + "...") if len(obj.description) > 75 else obj.description
        return "-"
    short_description.short_description = "Description"

    def plans_count(self, obj):
        return obj.plans.count()
    plans_count.short_description = "Number of Related Plans"
