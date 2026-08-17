"""Wagtail admin integration for the core app."""
from __future__ import annotations

from .models import CoreGroup


def register():
    from wagtail.snippets.models import register_snippet

    register_snippet(CoreGroup)
