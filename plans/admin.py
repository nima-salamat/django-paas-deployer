from django.contrib import admin
from .models import Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
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

