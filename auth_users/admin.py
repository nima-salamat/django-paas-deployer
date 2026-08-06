from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import LoginSettings, AuthCode, InviteLink, InviteUsage


@admin.register(LoginSettings)
class LoginSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "is_active",
        "allow_username",
        "allow_email",
        "allow_phone",
        "require_otp",
        "require_password",
        "allow_auto_signup",
        "require_invite_for_signup",
        "updated_at",
    )
    list_filter = ("is_active",)
    readonly_fields = ("updated_at",)

    fieldsets = (
        (
            "Identifiers",
            {
                "fields": ("allow_username", "allow_email", "allow_phone"),
            },
        ),
        (
            "Authentication factors",
            {
                "fields": ("require_otp", "require_password", "password_as_second_factor"),
            },
        ),
        (
            "Signup / activation",
            {
                "fields": (
                    "allow_auto_signup",
                    "require_invite_for_signup",
                    "auto_activate_on_signup",
                    "require_password_on_signup",
                    "activate_after_successful_otp",
                ),
                "description": (
                    "When allow_auto_signup=False (or require_invite_for_signup=True), "
                    "new accounts can only be created with a valid invite link."
                ),
            },
        ),
        (
            "Username recovery",
            {
                "fields": (
                    "allow_username_recovery",
                    "recovery_via_email",
                    "recovery_via_phone",
                ),
            },
        ),
        (
            "OTP settings",
            {
                "fields": ("otp_length", "otp_expire_minutes", "otp_max_attempts"),
            },
        ),
        (
            "Status",
            {
                "fields": ("is_active", "updated_at"),
            },
        ),
    )

    def has_add_permission(self, request):
        if LoginSettings.objects.exists():
            return False
        return super().has_add_permission(request)


class InviteUsageInline(admin.TabularInline):
    model = InviteUsage
    extra = 0
    readonly_fields = ("user", "used_at", "ip_address", "user_agent")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(InviteLink)
class InviteLinkAdmin(admin.ModelAdmin):
    list_display = (
        "short_token",
        "label",
        "uses_display",
        "is_active",
        "is_valid_display",
        "expires_at",
        "created_by",
        "created_at",
        "invite_url_display",
    )
    list_filter = ("is_active", "created_at")
    search_fields = ("token", "label", "created_by__username")
    readonly_fields = (
        "token",
        "uses_count",
        "created_at",
        "updated_at",
        "is_valid_display",
        "invite_url_display",
    )
    inlines = [InviteUsageInline]
    actions = ["deactivate_invites"]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "token",
                    "label",
                    "created_by",
                    "max_uses",
                    "uses_count",
                    "is_active",
                    "expires_at",
                    "is_valid_display",
                    "invite_url_display",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    @admin.display(description="Token")
    def short_token(self, obj):
        return obj.token[:16] + "…"

    @admin.display(description="Uses")
    def uses_display(self, obj):
        if obj.max_uses is None:
            return f"{obj.uses_count} / ∞"
        return f"{obj.uses_count} / {obj.max_uses}"

    @admin.display(boolean=True, description="Valid")
    def is_valid_display(self, obj):
        return obj.is_valid()

    @admin.display(description="Invite URL")
    def invite_url_display(self, obj):
        # Change base_url to your real domain in production
        url = obj.get_invite_url("https://echonode.website")
        return format_html('<a href="{}" target="_blank">{}</a>', url, url)

    @admin.action(description="Deactivate selected invites")
    def deactivate_invites(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(InviteUsage)
class InviteUsageAdmin(admin.ModelAdmin):
    list_display = ("user", "invite_short", "used_at", "ip_address")
    list_filter = ("used_at",)
    search_fields = ("user__username", "user__email", "invite__token", "invite__label")
    readonly_fields = ("invite", "user", "used_at", "ip_address", "user_agent")

    @admin.display(description="Invite")
    def invite_short(self, obj):
        return obj.invite.token[:16] + "…"


@admin.register(AuthCode)
class AuthCodeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_display",
        "contact",
        "purpose",
        "code",
        "attempts",
        "created_at",
        "updated_at",
        "is_expired_display",
        "is_locked_display",
    )
    list_filter = ("purpose", "created_at")
    search_fields = ("user__username", "user__email", "contact", "code")
    readonly_fields = ("created_at", "updated_at", "is_expired_display", "is_locked_display")
    ordering = ("-updated_at",)

    @admin.display(description="User")
    def user_display(self, obj):
        return obj.user.username if obj.user else "—"

    @admin.display(boolean=True, description="Expired")
    def is_expired_display(self, obj):
        return obj.is_expired()

    @admin.display(boolean=True, description="Locked")
    def is_locked_display(self, obj):
        return obj.is_locked()
