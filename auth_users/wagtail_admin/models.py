"""Wagtail admin (snippet) registration for the auth_users app."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from auth_users.models import AuthCode, InviteLink, InviteUsage, LoginSettings
from cms.wagtail_admin.utils import panels_for
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup


class LoginSettingsViewSet(SnippetViewSet):
    model = LoginSettings
    icon = "lock"
    menu_label = _("Login settings")
    menu_order = 120
    list_display = [
        "is_active",
        "allow_login",
        "allow_username",
        "allow_email",
        "allow_phone",
        "updated_at",
    ]
    list_filter = ["is_active", "allow_login"]
    panels = [
        MultiFieldPanel(
            [
                FieldPanel("is_active"),
                FieldPanel("allow_login"),
                FieldPanel("custom_login_closed_title"),
                FieldPanel("custom_login_closed_message"),
            ],
            heading=_("Master switch"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("allow_username"),
                FieldPanel("allow_email"),
                FieldPanel("allow_phone"),
            ],
            heading=_("Allowed identifiers"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("require_password"),
                FieldPanel("require_otp"),
                FieldPanel("password_as_second_factor"),
            ],
            heading=_("Authentication factors"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("allow_auto_signup"),
                FieldPanel("require_invite_for_signup"),
                FieldPanel("auto_activate_on_signup"),
                FieldPanel("require_password_on_signup"),
                FieldPanel("activate_after_successful_otp"),
            ],
            heading=_("Signup / activation"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("allow_username_recovery"),
                FieldPanel("recovery_via_email"),
                FieldPanel("recovery_via_phone"),
            ],
            heading=_("Username recovery"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("allow_password_recovery"),
                FieldPanel("password_recovery_via_email"),
                FieldPanel("password_recovery_via_phone"),
                FieldPanel("require_confirm_password"),
                FieldPanel("min_password_length"),
            ],
            heading=_("Password recovery"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("otp_length"),
                FieldPanel("otp_expire_minutes"),
                FieldPanel("otp_max_attempts"),
            ],
            heading=_("OTP settings"),
        ),
        FieldPanel("updated_at", read_only=True),
    ]


class InviteLinkViewSet(SnippetViewSet):
    model = InviteLink
    icon = "link"
    menu_label = _("Invite links")
    menu_order = 121
    list_display = [
        "token",
        "label",
        "uses_count",
        "max_uses",
        "is_active",
        "expires_at",
        "created_at",
    ]
    search_fields = ["token", "label", "created_by__username"]
    list_filter = ["is_active", "created_at"]
    ordering = ["-created_at"]
    panels = panels_for(
        editable=["label", "created_by", "max_uses", "is_active", "expires_at"],
        read_only=["token", "uses_count", "created_at", "updated_at"],
    )


class InviteUsageViewSet(SnippetViewSet):
    model = InviteUsage
    icon = "link"
    menu_label = _("Invite usage")
    menu_order = 122
    list_display = ["user", "invite", "used_at", "ip_address"]
    search_fields = ["user__username", "invite__token", "ip_address"]
    ordering = ["-used_at"]
    panels = panels_for(
        editable=[],
        read_only=["invite", "user", "used_at", "ip_address", "user_agent"],
    )


class AuthCodeViewSet(SnippetViewSet):
    model = AuthCode
    icon = "key"
    menu_label = _("Auth codes")
    menu_order = 123
    list_display = ["user", "contact", "purpose", "attempts", "created_at", "updated_at"]
    list_filter = ["purpose"]
    search_fields = ["user__username", "contact"]
    ordering = ["-updated_at"]
    panels = panels_for(
        editable=["user", "contact", "purpose"],
        read_only=["code", "attempts", "created_at", "updated_at"],
    )


class AuthUsersGroup(SnippetViewSetGroup):
    items = (
        LoginSettingsViewSet,
        InviteLinkViewSet,
        InviteUsageViewSet,
        AuthCodeViewSet,
    )
    menu_label = _("Auth")
    menu_icon = "lock"
    menu_order = 120
