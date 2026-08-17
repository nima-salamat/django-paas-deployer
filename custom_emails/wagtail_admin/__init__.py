"""Wagtail admin integration for the custom_emails app."""
from __future__ import annotations

from .models import EmailLogViewSet, EmailTemplateViewSet


def register():
    from wagtail.snippets.models import register_snippet

    register_snippet(EmailTemplateViewSet)
    register_snippet(EmailLogViewSet)
