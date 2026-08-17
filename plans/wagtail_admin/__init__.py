"""Wagtail admin integration for the plans app."""
from __future__ import annotations

from .models import PlansGroup


def register():
    from wagtail.snippets.models import register_snippet

    register_snippet(PlansGroup)
