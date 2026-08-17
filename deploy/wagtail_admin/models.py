"""Wagtail admin (snippet) registration for the deploy app."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from cms.wagtail_admin.utils import panels_for
from deploy.models import Deploy
from wagtail.snippets.views.snippets import SnippetViewSet


class DeployViewSet(SnippetViewSet):
    model = Deploy
    icon = "upload"
    menu_label = _("Deployments")
    menu_order = 104
    list_display = [
        "name",
        "service",
        "version",
        "status",
        "stage",
        "progress",
        "started_at",
        "created_at",
    ]
    list_filter = ["status", "rollback_status", "service"]
    search_fields = ["name", "service__name", "status_message", "error_message"]
    ordering = ["-created_at"]
    list_per_page = 50
    panels = panels_for(
        editable=["name", "service", "version", "zip_file"],
        read_only=[
            "id",
            "config",
            "started_at",
            "completed_at",
            "updated_file_at",
            "status",
            "stage",
            "progress",
            "status_message",
            "error_message",
            "rollback_status",
            "health_status",
            "container_status",
            "image_status",
            "volume_status",
            "network_status",
            "cancel_requested",
            "created_at",
            "updated_at",
        ],
    )
