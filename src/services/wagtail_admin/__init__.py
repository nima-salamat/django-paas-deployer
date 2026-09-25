"""Wagtail admin integration for the services app."""
from __future__ import annotations

from .models import ServicesGroup


def register():
    from wagtail.snippets.models import register_snippet

    register_snippet(ServicesGroup)
