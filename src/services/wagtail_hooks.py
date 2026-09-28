"""Wagtail hooks for the services operator surface."""
from __future__ import annotations

from django.urls import path, reverse
from django.utils.http import urlencode
from wagtail import hooks
from wagtail.snippets import widgets as wagtailsnippets_widgets

from services.models import Service
from services.wagtail_admin import register as _register_services

_register_services()


@hooks.register("register_admin_urls")
def register_service_admin_urls():
    from services.wagtail_admin.views import service_inspect
    return [
        path("services/<uuid:pk>/inspect/", service_inspect, name="wagtail_services_service_inspect"),
    ]


@hooks.register("register_snippet_listing_buttons")
def service_listing_buttons(snippet, user, next_url=None):
    if not isinstance(snippet, Service):
        return
    if not getattr(user, "is_staff", False):
        return
    if not (getattr(user, "is_superuser", False) or user.has_perm("services.view_service")):
        return
    query = urlencode({"next": next_url}) if next_url else ""
    suffix = f"?{query}" if query else ""
    yield wagtailsnippets_widgets.SnippetListingButton(
        "Inspect service",
        reverse("wagtail_services_service_inspect", kwargs={"pk": snippet.pk}) + suffix,
        priority=10,
    )
