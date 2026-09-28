"""Explicit Wagtail surfaces for catalog-installed application state."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from app_catalog.models import ApplicationInstance, ApplicationInstanceService
from cms.wagtail_admin.utils import ReadOnlyModelPermissionPolicy, panels_for
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup


class ApplicationInstanceViewSet(SnippetViewSet):
    model = ApplicationInstance
    permission_policy = ReadOnlyModelPermissionPolicy(ApplicationInstance)
    inspect_view_enabled = True
    copy_view_enabled = False
    icon = "site"
    menu_label = _("Installed applications")
    menu_order = 180
    list_display = ["name", "catalog_id", "definition_version", "variant_id", "status", "stage", "error_code", "created_at", "deployed_at"]
    list_filter = ["status", "catalog_id", "variant_id", "created_at"]
    search_fields = ["name", "slug", "catalog_id", "error_code", "error_message", "execution_task_id"]
    ordering = ["-created_at"]
    list_per_page = 50
    panels = panels_for(editable=[], read_only=["id", "user", "name", "slug", "catalog_id", "definition_version", "software_version", "variant_id", "config", "status", "stage", "error_code", "error_message", "created_at", "updated_at", "deployed_at", "execution_task_id", "started_at", "execution_deadline", "cancel_requested", "network"])


class ApplicationInstanceServiceViewSet(SnippetViewSet):
    model = ApplicationInstanceService
    permission_policy = ReadOnlyModelPermissionPolicy(ApplicationInstanceService)
    inspect_view_enabled = True
    copy_view_enabled = False
    icon = "link"
    menu_label = _("Application service bindings")
    menu_order = 181
    list_display = ["instance", "service_key", "service", "deploy", "sequence", "dispatch_task_id", "dispatched_at"]
    list_filter = ["service_key", "sequence", "dispatched_at"]
    search_fields = ["service_key", "dispatch_task_id", "instance__name", "service__name"]
    ordering = ["instance", "sequence", "service_key"]
    list_per_page = 100
    panels = panels_for(editable=[], read_only=["id", "instance", "service", "deploy", "service_key", "sequence", "dispatch_task_id", "dispatched_at"])


class ApplicationCatalogGroup(SnippetViewSetGroup):
    items = (ApplicationInstanceViewSet, ApplicationInstanceServiceViewSet)
    menu_label = _("Applications")
    menu_icon = "site"
    menu_order = 180
