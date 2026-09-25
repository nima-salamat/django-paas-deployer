"""Wagtail home-page panels for live system gauges."""
from __future__ import annotations

from django.urls import reverse
from django.utils.safestring import mark_safe
from wagtail.admin.ui.components import Component


class SystemGaugesPanel(Component):
    """Two live gauges (CPU + RAM) on the Wagtail admin home page."""

    name = "system_gauges"
    order = 50
    template_name = "wagtailadmin/home/system_gauges.html"

    def get_context_data(self, parent_context):
        context = super().get_context_data(parent_context)
        request = parent_context.get("request")
        metrics_url = reverse("wagtail_core_system_metrics")
        context["metrics_url"] = metrics_url
        context["request"] = request
        return context
