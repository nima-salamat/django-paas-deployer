"""Wagtail admin integration for the plans app."""
from __future__ import annotations

from .models import PlanViewSet


def register():
    from wagtail.snippets.models import register_snippet

    register_snippet(PlanViewSet)
