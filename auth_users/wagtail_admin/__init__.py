"""Wagtail admin integration for the auth_users app."""
from __future__ import annotations

from .models import AuthUsersGroup


def register():
    from wagtail.snippets.models import register_snippet

    register_snippet(AuthUsersGroup)
