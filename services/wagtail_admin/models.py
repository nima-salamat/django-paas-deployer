"""Wagtail admin (snippet) registration for the services app."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from cms.wagtail_admin.utils import panels_for
from services.models import PrivateNetwork, Service, Volume
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup


class PrivateNetworkViewSet(SnippetViewSet):
    model = PrivateNetwork
    icon = "globe"
    menu_label = _("Private networks")
    menu_order = 101
    list_display = ["name", "user", "description", "created_at"]
    search_fields = ["name", "user__username", "description"]
    list_filter = ["user"]
    panels = panels_for(
        editable=["name", "user", "description"],
        read_only=["id", "created_at", "updated_at"],
    )


class ServiceViewSet(SnippetViewSet):
    model = Service
    icon = "cog"
    menu_label = _("Services")
    menu_order = 102
    list_display = ["name", "user", "plan", "network", "status", "deployed_at", "created_at"]
    list_filter = ["status", "plan", "user", "read_only"]
    search_fields = ["name", "user__username", "plan__name"]
    panels = panels_for(
        editable=["name", "user", "plan", "network", "selected_deploy", "read_only"],
        read_only=[
            "id",
            "selected_deploy_at",
            "deploy_started",
            "deployed_at",
            "status",
            "task_id",
            "created_at",
            "updated_at",
        ],
    )


class VolumeViewSet(SnippetViewSet):
    model = Volume
    icon = "cog"
    menu_label = _("Volumes")
    menu_order = 103
    list_display = ["name", "user", "service", "size_mb", "default_mode", "created_at"]
    search_fields = ["name", "user__username", "service__name"]
    list_filter = ["default_mode", "user"]
    panels = panels_for(
        editable=["name", "user", "service", "size_mb", "default_bind", "default_mode"],
        read_only=["id", "service_attachments", "created_at", "updated_at"],
    )


class ServicesGroup(SnippetViewSetGroup):
    items = (
        ServiceViewSet,
        VolumeViewSet,
        PrivateNetworkViewSet,
    )
    menu_label = _("Services")
    menu_icon = "cog"
    menu_order = 100
