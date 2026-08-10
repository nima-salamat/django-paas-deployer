from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.urls import reverse
from .models import LoginSettings, AuthCode, InviteLink, InviteUsage


# ─────────────────────────────────────────────────────────────
# Login Settings (Singleton)
# ─────────────────────────────────────────────────────────────
@admin.register(LoginSettings)
class LoginSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "status_badge",
        "login_status_badge",
        "identifiers_summary",
        "factors_summary",
        "signup_summary",
        "otp_summary",
        "updated_at",
    )
    list_filter = ("is_active", "allow_login", "allow_password_recovery")
    readonly_fields = ("updated_at",)
    actions = None

    fieldsets = (
        (
            "Identifiers",
            {
                "fields": ("allow_username", "allow_email", "allow_phone"),
                "description": "Which identifiers users can use to log in or sign up.",
            },
        ),
        (
            "Authentication factors",
            {
                "fields": ("require_otp", "require_password", "password_as_second_factor"),
                "description": "OTP and/or password requirements for authentication.",
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
            "Login master switch",
            {
                "fields": (
                    "allow_login",
                    "custom_login_closed_title",
                    "custom_login_closed_message",
                ),
                "description": (
                    "When allow_login=False the entire login/signup UI is blocked "
                    "and the custom title + message are shown to users."
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
            "Password recovery (Forgot Password)",
            {
                "fields": (
                    "allow_password_recovery",
                    "password_recovery_via_email",
                    "password_recovery_via_phone",
                    "require_confirm_password",
                    "min_password_length",
                ),
                "description": (
                    "Enable/disable forgot-password flow and control channels + password rules."
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

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Status", ordering="is_active")
    def status_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span class="badge badge-success">Active</span>'
            )
        return format_html(
            '<span class="badge badge-gray">Inactive</span>'
        )

    @admin.display(description="Login", ordering="allow_login")
    def login_status_badge(self, obj):
        if obj.allow_login:
            return format_html('<span class="badge badge-success">Open</span>')
        return format_html('<span class="badge badge-danger">Closed</span>')

    @admin.display(description="Identifiers")
    def identifiers_summary(self, obj):
        parts = []
        if obj.allow_username:
            parts.append("username")
        if obj.allow_email:
            parts.append("email")
        if obj.allow_phone:
            parts.append("phone")
        return ", ".join(parts) or "—"

    @admin.display(description="Factors")
    def factors_summary(self, obj):
        parts = []
        if obj.require_otp:
            parts.append("OTP")
        if obj.require_password:
            parts.append("Password")
        if obj.password_as_second_factor:
            parts.append("2FA")
        return " + ".join(parts) or "—"

    @admin.display(description="Signup")
    def signup_summary(self, obj):
        if obj.require_invite_for_signup:
            return format_html('<span class="badge badge-warning">Invite only</span>')
        if obj.allow_auto_signup:
            return format_html('<span class="badge badge-success">Open</span>')
        return format_html('<span class="badge badge-danger">Closed</span>')

    @admin.display(description="OTP")
    def otp_summary(self, obj):
        return f"{obj.otp_length} dig · {obj.otp_expire_minutes}m · max {obj.otp_max_attempts}"


# ─────────────────────────────────────────────────────────────
# Invite Usage (Inline)
# ─────────────────────────────────────────────────────────────
class InviteUsageInline(admin.TabularInline):
    model = InviteUsage
    extra = 0
    readonly_fields = ("user", "used_at", "ip_address", "user_agent_short")
    can_delete = False
    fields = ("user", "used_at", "ip_address", "user_agent_short")
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="User Agent")
    def user_agent_short(self, obj):
        ua = obj.user_agent or ""
        return (ua[:60] + "…") if len(ua) > 60 else (ua or "—")


# ─────────────────────────────────────────────────────────────
# Invite Link
# ─────────────────────────────────────────────────────────────
@admin.register(InviteLink)
class InviteLinkAdmin(admin.ModelAdmin):
    list_display = (
        "short_token",
        "label",
        "uses_display",
        "status_badge",
        "is_valid_display",
        "expires_at",
        "created_by",
        "created_at",
        "invite_url_display",
    )
    list_filter = ("is_active", "created_at", "expires_at")
    search_fields = ("token", "label", "created_by__username", "created_by__email")
    readonly_fields = (
        "token",
        "uses_count",
        "created_at",
        "updated_at",
        "is_valid_display",
        "invite_url_display",
        "remaining_display",
    )
    autocomplete_fields = ("created_by",)
    inlines = [InviteUsageInline]
    actions = ["deactivate_invites", "activate_invites"]
    date_hierarchy = "created_at"
    list_per_page = 30
    ordering = ("-created_at",)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "token",
                    "label",
                    "created_by",
                ),
            },
        ),
        (
            "Usage limits",
            {
                "fields": (
                    "max_uses",
                    "uses_count",
                    "remaining_display",
                    "is_active",
                    "expires_at",
                    "is_valid_display",
                ),
            },
        ),
        (
            "Invite URL",
            {
                "fields": ("invite_url_display",),
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

    @admin.display(description="Token")
    def short_token(self, obj):
        return format_html(
            '<code style="font-size:12px;background:#161b22;padding:2px 6px;'
            'border-radius:4px;color:#8b949e;">{}…</code>',
            obj.token[:16],
        )

    @admin.display(description="Uses")
    def uses_display(self, obj):
        if obj.max_uses is None:
            return format_html(
                '<span style="color:#22c55e;font-weight:600;">{} / ∞</span>',
                obj.uses_count,
            )
        color = "#ef4444" if obj.uses_count >= obj.max_uses else "#3b82f6"
        return format_html(
            '<span style="color:{};font-weight:600;">{} / {}</span>',
            color,
            obj.uses_count,
            obj.max_uses,
        )

    @admin.display(description="Remaining")
    def remaining_display(self, obj):
        rem = obj.remaining_uses()
        if rem is None:
            return "Unlimited"
        return rem

    @admin.display(description="Status", ordering="is_active")
    def status_badge(self, obj):
        if not obj.is_active:
            return format_html('<span class="badge badge-gray">Disabled</span>')
        if obj.is_expired():
            return format_html('<span class="badge badge-danger">Expired</span>')
        if obj.is_exhausted():
            return format_html('<span class="badge badge-warning">Exhausted</span>')
        return format_html('<span class="badge badge-success">Active</span>')

    @admin.display(boolean=True, description="Valid")
    def is_valid_display(self, obj):
        return obj.is_valid()

    @admin.display(description="Invite URL")
    def invite_url_display(self, obj):
        # Change base_url to your real domain in production
        url = obj.get_invite_url("https://echonode.website")
        return format_html(
            '<a href="{}" target="_blank" rel="noopener" '
            'style="font-size:12px;word-break:break-all;">{}</a>',
            url,
            url,
        )

    @admin.action(description="Deactivate selected invites")
    def deactivate_invites(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} invite(s) deactivated.")

    @admin.action(description="Activate selected invites")
    def activate_invites(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} invite(s) activated.")


# ─────────────────────────────────────────────────────────────
# Invite Usage
# ─────────────────────────────────────────────────────────────
@admin.register(InviteUsage)
class InviteUsageAdmin(admin.ModelAdmin):
    list_display = ("user", "invite_short", "used_at", "ip_address")
    list_filter = ("used_at",)
    search_fields = (
        "user__username",
        "user__email",
        "invite__token",
        "invite__label",
        "ip_address",
    )
    readonly_fields = ("invite", "user", "used_at", "ip_address", "user_agent")
    date_hierarchy = "used_at"
    ordering = ("-used_at",)
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Invite")
    def invite_short(self, obj):
        return format_html(
            '<code style="font-size:12px;">{}…</code>',
            obj.invite.token[:16],
        )


# ─────────────────────────────────────────────────────────────
# Auth Code (OTP)
# ─────────────────────────────────────────────────────────────
@admin.register(AuthCode)
class AuthCodeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_display",
        "contact",
        "purpose_badge",
        "code_display",
        "attempts_display",
        "created_at",
        "updated_at",
        "is_expired_display",
        "is_locked_display",
    )
    list_filter = ("purpose", "created_at")
    search_fields = ("user__username", "user__email", "contact", "code")
    readonly_fields = (
        "created_at",
        "updated_at",
        "is_expired_display",
        "is_locked_display",
    )
    ordering = ("-updated_at",)
    list_per_page = 40
    date_hierarchy = "created_at"
    actions = ["invalidate_codes"]

    @admin.display(description="User")
    def user_display(self, obj):
        if obj.user:
            return obj.user.username
        return format_html('<span style="color:#8b949e;">—</span>')

    @admin.display(description="Purpose")
    def purpose_badge(self, obj):
        colors = {
            "login": "badge-primary",
            "signup": "badge-success",
            "recovery": "badge-warning",
            "password_reset": "badge-danger",
        }
        cls = colors.get(obj.purpose, "badge-gray")
        return format_html(
            '<span class="badge {}">{}</span>',
            cls,
            obj.get_purpose_display(),
        )

    @admin.display(description="Code")
    def code_display(self, obj):
        return format_html(
            '<code style="font-size:13px;letter-spacing:0.08em;'
            'background:#161b22;padding:3px 8px;border-radius:4px;">{}</code>',
            obj.code,
        )

    @admin.display(description="Attempts")
    def attempts_display(self, obj):
        from .models import LoginSettings
        s = LoginSettings.get_solo()
        max_a = s.otp_max_attempts
        color = "#ef4444" if obj.attempts >= max_a else "#22c55e" if obj.attempts == 0 else "#f59e0b"
        return format_html(
            '<span style="color:{};font-weight:600;">{} / {}</span>',
            color,
            obj.attempts,
            max_a,
        )

    @admin.display(boolean=True, description="Expired")
    def is_expired_display(self, obj):
        if obj is None or getattr(obj, "pk", None) is None:
            return False
        return obj.is_expired()

    @admin.display(boolean=True, description="Locked")
    def is_locked_display(self, obj):
        if obj is None or getattr(obj, "pk", None) is None:
            return False
        return obj.is_locked()
    
    @admin.action(description="Invalidate (delete) selected codes")
    def invalidate_codes(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f"{count} auth code(s) deleted.")
