"""Wagtail admin integration for the deploy app."""
from __future__ import annotations

from .models import DeployGroup


def register():
    from wagtail.snippets.models import register_snippet

    register_snippet(DeployGroup)
