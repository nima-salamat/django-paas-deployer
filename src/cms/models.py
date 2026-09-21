"""
Minimal Wagtail page models.

We intentionally keep a single HomePage type so Wagtail's site tree is valid
in production, without shipping the default "Welcome to Wagtail!" content.
"""
from __future__ import annotations

from django.db import models
from wagtail.models import Page
from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField


class HomePage(Page):
    """Root-level site homepage (API-first project — page is a structural root only)."""

    body = RichTextField(blank=True, default="")

    content_panels = Page.content_panels + [
        FieldPanel("body"),
    ]

    # No subpages required for pure-admin usage
    subpage_types: list[str] = []
    parent_page_types: list[str] = ["wagtailcore.Page"]

    class Meta:
        verbose_name = "Home page"
        verbose_name_plural = "Home pages"
