"""Wagtail admin integration for the auth_users app."""
from __future__ import annotations

from .models import (
    AuthCodeViewSet,
    InviteLinkViewSet,
    InviteUsageViewSet,
    LoginSettingsViewSet,
)


def register():
    from wagtail.snippets.models import register_snippet

    register_snippet(LoginSettingsViewSet)
    register_snippet(InviteLinkViewSet)
    register_snippet(InviteUsageViewSet)
    register_snippet(AuthCodeViewSet)
