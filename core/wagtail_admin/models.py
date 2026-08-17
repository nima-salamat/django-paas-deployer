"""Wagtail admin (snippet) registration for the core app."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from cms.wagtail_admin.utils import panels_for
from core.models import SystemSetting
from wagtail.snippets.views.snippets import SnippetViewSet


class SystemSettingViewSet(SnippetViewSet):
    model = SystemSetting
    icon = "cog"
    menu_label = _("System settings")
    menu_order = 110
    list_display = [
        "key",
        "category",
        "label",
        "value_type",
        "is_secret",
        "is_editable",
        "updated_at",
    ]
    list_filter = ["category", "value_type", "is_secret", "is_editable"]
    search_fields = ["key", "label", "description", "value"]
    ordering = ["category", "key"]
    list_per_page = 50
    panels = panels_for(
        editable=[
            "label",
            "category",
            "description",
            "value_type",
            "value",
            "is_secret",
            "is_editable",
        ],
        read_only=["key", "created_at", "updated_at"],
    )
