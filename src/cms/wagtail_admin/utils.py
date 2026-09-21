"""
Shared helpers for per-app Wagtail admin (snippet) registration.

These keep the per-app ``wagtail_admin`` view sets concise without coupling
the app modules to each other.
"""
from __future__ import annotations

from wagtail.admin.panels import FieldPanel


def panels_for(editable, read_only=()):
    """Build a list of FieldPanels.

    ``editable`` fields are writable; ``read_only`` fields are displayed but
    not editable (e.g. generated UUIDs, auto timestamps, tokens, secrets).
    """
    panels = [FieldPanel(f) for f in editable]
    panels += [FieldPanel(f, read_only=True) for f in read_only]
    return panels


def read_only_panels(fields):
    """Build read-only FieldPanels for a list of field names."""
    return [FieldPanel(f, read_only=True) for f in fields]
