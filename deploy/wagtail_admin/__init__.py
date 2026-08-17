"""Wagtail admin integration for the deploy app."""
from __future__ import annotations

from .models import DeployLogViewSet, DeployViewSet


def register():
    from wagtail.snippets.models import register_snippet

    register_snippet(DeployViewSet)
    register_snippet(DeployLogViewSet)
