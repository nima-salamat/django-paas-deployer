"""Wagtail admin (snippet) registration for the plans app."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from cms.wagtail_admin.utils import panels_for
from plans.models import Plan
from wagtail.snippets.views.snippets import SnippetViewSet


class PlanViewSet(SnippetViewSet):
    model = Plan
    icon = "doc-full-inverse"
    menu_label = _("Plans")
    menu_order = 100
    list_display = [
        "name",
        "platform",
        "plan_type",
        "max_cpu",
        "max_ram",
        "max_storage",
        "price_per_hour",
        "created_at",
    ]
    list_filter = ["platform", "plan_type", "storage_type", "name"]
    search_fields = ["name", "platform"]
    ordering = ["name", "platform"]
    list_per_page = 50
    panels = panels_for(
        editable=[
            "name",
            "platform",
            "plan_type",
            "max_cpu",
            "max_ram",
            "max_storage",
            "price_per_hour",
            "storage_type",
        ],
        read_only=["id", "created_at", "updated_at"],
    )
