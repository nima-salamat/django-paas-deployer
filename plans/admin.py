from django.contrib import admin
from django.utils.html import format_html
from .models import Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name_badge",
        "platform_badge",
        "plan_type_badge",
        "max_cpu",
        "max_ram_display",
        "max_storage_display",
        "storage_type",
        "formatted_price",
        "price_day",
        "price_month",
        "created_at",
        "updated_at",
    )
    list_filter = ("platform", "plan_type", "storage_type", "name")
    search_fields = ("name", "platform")
    ordering = ("name", "platform")
    list_per_page = 30
    readonly_fields = ("created_at", "updated_at", "price_per_day_display", "price_per_month_display")

    fieldsets = (
        (
            "Plan identity",
            {
                "fields": ("name", "platform", "plan_type"),
            },
        ),
        (
            "Resources",
            {
                "fields": (
                    "max_cpu",
                    "max_ram",
                    "max_storage",
                    "storage_type",
                ),
            },
        ),
        (
            "Pricing (Toman)",
            {
                "fields": (
                    "price_per_hour",
                    "price_per_day_display",
                    "price_per_month_display",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Name", ordering="name")
    def name_badge(self, obj):
        colors = {
            "bronze": "#cd7f32",
            "silver": "#94a3b8",
            "gold": "#eab308",
            "platinum": "#a855f7",
            "diamond": "#06b6d4",
        }
        key = str(obj.name).lower()
        color = colors.get(key, "#3b82f6")
        return format_html(
            '<span class="badge" style="background:{};">{}</span>',
            color,
            obj.get_name_display() if hasattr(obj, "get_name_display") else obj.name,
        )

    @admin.display(description="Platform", ordering="platform")
    def platform_badge(self, obj):
        return format_html(
            '<span class="badge badge-primary">{}</span>',
            obj.get_platform_display() if hasattr(obj, "get_platform_display") else obj.platform,
        )

    @admin.display(description="Type", ordering="plan_type")
    def plan_type_badge(self, obj):
        return format_html(
            '<span class="badge badge-info">{}</span>',
            obj.get_plan_type_display() if hasattr(obj, "get_plan_type_display") else obj.plan_type,
        )

    @admin.display(description="RAM", ordering="max_ram")
    def max_ram_display(self, obj):
        return f"{obj.max_ram:,.0f} MB"

    @admin.display(description="Storage", ordering="max_storage")
    def max_storage_display(self, obj):
        return f"{obj.max_storage} GB"

    @admin.display(description="Price / Hour", ordering="price_per_hour")
    def formatted_price(self, obj):
        return format_html(
            '<span style="font-weight:600;color:#22c55e;">{} Toman</span>',
            f"{obj.price_per_hour:,.0f}",
        )

    @admin.display(description="Price / Day")
    def price_day(self, obj):
        return f"{obj.price_per_day:,.0f}"

    @admin.display(description="Price / Month")
    def price_month(self, obj):
        return f"{obj.price_per_month:,.0f}"

    @admin.display(description="Price per Day")
    def price_per_day_display(self, obj):
        return f"{obj.price_per_day:,.0f} Toman"

    @admin.display(description="Price per Month")
    def price_per_month_display(self, obj):
        return f"{obj.price_per_month:,.0f} Toman"
