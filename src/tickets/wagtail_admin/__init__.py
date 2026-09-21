"""Wagtail admin integration for the tickets app."""
from __future__ import annotations

from .models import TicketsGroup


def register():
    from wagtail.snippets.models import register_snippet

    register_snippet(TicketsGroup)
