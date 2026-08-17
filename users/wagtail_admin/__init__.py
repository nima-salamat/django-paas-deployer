"""Wagtail admin integration for the users app."""
from __future__ import annotations

from .models import ProfileViewSet, ReceiptViewSet, RuleViewSet


def register():
    from wagtail.snippets.models import register_snippet

    register_snippet(ReceiptViewSet)
    register_snippet(ProfileViewSet)
    register_snippet(RuleViewSet)
