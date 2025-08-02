from django.contrib import admin
from .models import Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "platform",
        "plan_type",
        "max_cpu",
        "max_ram",
        "max_storage",
        "storage_type",
        "formatted_price",
        "created_at",
        "updated_at",
    )
    list_display_links = ("id", "name")
    search_fields = ("name", "platform")
    ordering = ("name",)
    list_filter = ("plan_type", "storage_type", "platform", "name")
    list_per_page = 25

    readonly_fields = ("created_at", "updated_at")

    def formatted_price(self, obj):
        return f"{obj.price:,.0f} Toman"
    formatted_price.short_description = "Price"
    formatted_price.admin_order_field = "price"

    fieldsets = (
        (None, {
            "fields": (
                "name",
                "platform",
                "plan_type",
                "storage_type",
                "max_cpu",
                "max_ram",
                "max_storage",
                "price",
            )
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
