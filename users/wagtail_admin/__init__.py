"""Wagtail admin integration for the users app."""
from __future__ import annotations

from .models import UsersGroup


def register():
    from wagtail.snippets.models import register_snippet

    register_snippet(UsersGroup)
