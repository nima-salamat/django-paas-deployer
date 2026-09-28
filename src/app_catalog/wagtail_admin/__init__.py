"""Register catalog installation operator surfaces in Wagtail."""
from __future__ import annotations

from .models import ApplicationCatalogGroup


def register():
    from wagtail.snippets.models import register_snippet
    register_snippet(ApplicationCatalogGroup)
