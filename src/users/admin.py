from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from users.models import User, Profile, Rule, Receipt
from django.contrib.auth.models import Group

# Unregister default Group (optional – keep if you still use Django groups)
try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


# ─────────────────────────────────────────────────────────────
# Profile Inline
# ─────────────────────────────────────────────────────────────
class ProfileInline(admin.TabularInline):
    model = Profile
    extra = 0
    fields = ("order", "image", "created_at")
    readonly_fields = ("created_at",)
    max_num = 5
    show_change_link = True


# ─────────────────────────────────────────────────────────────
# Rule Inline
# ─────────────────────────────────────────────────────────────
class RuleInline(admin.StackedInline):
    model = Rule
    extra = 0
    max_num = 1
    fields = ("rules", "updated_at", "created_at")
    readonly_fields = ("updated_at", "created_at")
    can_delete = True


# ─────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = (
        "id",
        "username",
        "email",
        "phone_number",
        "balance_display",
        "is_active_badge",
        "is_staff",
        "is_superuser",
        "email_verified",
        "phone_number_verified",
        "date_joined",
        "last_login",
    )
    list_display_links = ("id", "username")
    search_fields = ("username", "email", "phone_number", "uuid", "national_id")
    ordering = ("-date_joined",)
    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
        "email_verified",
        "phone_number_verified",
        "theme",
        "date_joined",
    )
    list_per_page = 30
    date_hierarchy = "date_joined"
    inlines = [ProfileInline, RuleInline]
    filter_horizontal = []
    readonly_fields = ("uuid", "date_joined", "last_login")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "username",
                    "password",
                    "uuid",
                ),
            },
        ),
        (
            "Contact",
            {
                "fields": (
                    "email",
                    "email_verified",
                    "phone_number",
                    "phone_number_verified",
                ),
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
        (
            "Profile & Preferences",
            {
                "fields": (
                    "theme",
                    "color",
                    "birthdate",
                    "national_id",
                ),
            },
        ),
        (
            "Wallet",
            {
                "fields": ("balance",),
            },
        ),
        (
            "Important dates",
            {
                "fields": ("last_login", "date_joined"),
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "phone_number",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_superuser",
                    "is_active",
                ),
            },
        ),
    )

    actions = ["activate_users", "deactivate_users"]

    @admin.display(description="Balance", ordering="balance")
    def balance_display(self, obj):
        value = obj.balance or 0
        color = "#22c55e" if value > 0 else "#8b949e"
        return format_html(
            '<span style="font-weight:600;color:{};">{}</span>',
            color,
            f"{value:,.3f}",
        )

    @admin.display(description="Active", ordering="is_active")
    def is_active_badge(self, obj):
        if obj.is_active:
            return format_html('<span class="badge badge-success">Active</span>')
        return format_html('<span class="badge badge-danger">Inactive</span>')

    @admin.action(description="Activate selected users")
    def activate_users(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} user(s) activated.")

    @admin.action(description="Deactivate selected users")
    def deactivate_users(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} user(s) deactivated.")


# ─────────────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────────────
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "user_link",
        "image_preview",
        "created_at",
    )
    list_display_links = ("id",)
    search_fields = ("user__username", "user__email", "id")
    list_filter = ("created_at",)
    ordering = ("-created_at",)
    list_per_page = 20
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "id", "image_preview")

    fieldsets = (
        (
            None,
            {
                "fields": ("user", "order", "image", "image_preview"),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at",),
            },
        ),
    )

    @admin.display(description="User", ordering="user__username")
    def user_link(self, obj):
        if not obj.user_id:
            return "—"
        url = reverse("admin:users_user_change", args=[obj.user_id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)

    @admin.display(description="Preview")
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:48px;max-width:80px;'
                'border-radius:6px;object-fit:cover;" />',
                obj.image.url,
            )
        return format_html('<span style="color:#6e7681;">—</span>')


# ─────────────────────────────────────────────────────────────
# Rule
# ─────────────────────────────────────────────────────────────
@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_link",
        "rules_preview",
        "updated_at",
        "created_at",
    )
    list_display_links = ("id",)
    search_fields = ("user__username", "user__email", "id")
    list_filter = ("created_at", "updated_at")
    ordering = ("-created_at",)
    list_per_page = 20
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at", "id")

    fieldsets = (
        (
            None,
            {
                "fields": ("user", "rules"),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    @admin.display(description="User", ordering="user__username")
    def user_link(self, obj):
        if not obj.user_id:
            return "—"
        url = reverse("admin:users_user_change", args=[obj.user_id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)

    @admin.display(description="Rules")
    def rules_preview(self, obj):
        rules = obj.rules or []
        if not rules:
            return format_html('<span style="color:#6e7681;">—</span>')
        preview = ", ".join(str(r) for r in rules[:5])
        if len(rules) > 5:
            preview += f" (+{len(rules) - 5})"
        return preview


# ─────────────────────────────────────────────────────────────
# Receipt (Wallet transactions)
# ─────────────────────────────────────────────────────────────
@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_link",
        "amount_display",
        "status_badge",
        "created_at",
        "updated_at",
    )
    list_display_links = ("id",)
    search_fields = ("user__username", "user__email", "id")
    list_filter = ("status", "created_at")
    ordering = ("-created_at",)
    list_per_page = 30
    date_hierarchy = "created_at"
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")
    actions = ["mark_as_paid"]

    fieldsets = (
        (
            None,
            {
                "fields": ("user", "amount", "status"),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    @admin.display(description="User", ordering="user__username")
    def user_link(self, obj):
        if not obj.user_id:
            return "—"
        url = reverse("admin:users_user_change", args=[obj.user_id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)

    @admin.display(description="Amount", ordering="amount")
    def amount_display(self, obj):
        value = obj.amount or 0
        color = "#22c55e" if value > 0 else "#ef4444"
        return format_html(
            '<span style="font-weight:600;color:{};">{}</span>',
            color,
            f"{value:,.3f}",
        )

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        # Adjust keys to match PaymentChoices
        colors = {
            "payed": "#16a34a",
            "paid": "#16a34a",
            "not_payed": "#6b7280",
            "pending": "#f59e0b",
            "failed": "#dc2626",
        }
        key = str(obj.status).lower()
        color = colors.get(key, "#6b7280")
        label = obj.get_status_display() if hasattr(obj, "get_status_display") else obj.status
        return format_html(
            '<span class="badge" style="background:{};">{}</span>',
            color,
            label,
        )

    @admin.action(description="Mark selected as paid & credit balance")
    def mark_as_paid(self, request, queryset):
        from users.models import Receipt as ReceiptModel
        count = 0
        for receipt in queryset.filter(status__in=["not_payed", "pending", "NOT_PAYED"]):
            try:
                ReceiptModel.change_balance(receipt)
                count += 1
            except Exception:
                pass
        self.message_user(request, f"{count} receipt(s) marked as paid and balance updated.")
