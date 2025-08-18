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

    def formatted_price(self, obj):
        return f"{obj.price_per_hour:,.0f} Toman"
    formatted_price.short_description = "Price per Hour"
