"""Wagtail admin integration for the messenger app."""
from __future__ import annotations

from .models import MessengerGroup


def register():
    from wagtail.snippets.models import register_snippet

    register_snippet(MessengerGroup)
