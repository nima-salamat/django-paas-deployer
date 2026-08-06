from django.contrib import admin
from .models import LoginSettings, AuthCode


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
        "password_as_second_factor",
        "allow_auto_signup",
        "updated_at",
    )
    list_filter = ("is_active",)
    readonly_fields = ("updated_at",)

    fieldsets = (
        (
            "Identifiers",
            {
                "fields": (
                    "allow_username",
                    "allow_email",
                    "allow_phone",
                ),
                "description": "Which fields can be used to identify a user.",
            },
        ),
        (
            "Authentication factors",
            {
                "fields": (
                    "require_otp",
                    "require_password",
                    "password_as_second_factor",
                ),
                "description": (
                    "require_otp → always send a code.\n"
                    "password_as_second_factor → after OTP ask for password if user has one.\n"
                    "require_password → password is mandatory when the user already has one."
                ),
            },
        ),
        (
            "Signup / activation",
            {
                "fields": (
                    "allow_auto_signup",
                    "auto_activate_on_signup",
                    "require_password_on_signup",
                    "activate_after_successful_otp",
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
                "fields": (
                    "otp_length",
                    "otp_expire_minutes",
                    "otp_max_attempts",
                ),
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
        # Prefer a single settings row
        if LoginSettings.objects.exists():
            return False
        return super().has_add_permission(request)


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
    search_fields = (
        "user__username",
        "user__email",
        "contact",
        "code",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "is_expired_display",
        "is_locked_display",
    )
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
