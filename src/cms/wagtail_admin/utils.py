"""
Shared helpers for per-app Wagtail admin (snippet) registration.
"""
from __future__ import annotations

from wagtail.admin.panels import FieldPanel
from wagtail.permission_policies.base import ModelPermissionPolicy


def panels_for(editable, read_only=()):
    """Build FieldPanels with an explicit writable/read-only boundary."""
    panels = [FieldPanel(f) for f in editable]
    panels += [FieldPanel(f, read_only=True) for f in read_only]
    return panels


def read_only_panels(fields):
    """Build read-only FieldPanels for a list of field names."""
    return [FieldPanel(f, read_only=True) for f in fields]


class ReadOnlyModelPermissionPolicy(ModelPermissionPolicy):
    """Allow inspection/listing while forbidding all model mutations."""

    def user_has_permission(self, user, action):
        if action in {"add", "change", "delete"}:
            return False
        return super().user_has_permission(user, action)

    def user_has_any_permission(self, user, actions):
        allowed = {action for action in actions if action not in {"add", "change", "delete"}}
        return super().user_has_any_permission(user, allowed)
