"""Wagtail hooks for catalog-installed application administration."""
from __future__ import annotations

from django.urls import path, reverse
from django.utils.http import urlencode
from wagtail import hooks
from wagtail.snippets import widgets as wagtailsnippets_widgets

from app_catalog.models import ApplicationInstance, ApplicationStatus
from app_catalog.wagtail_admin import register as _register_catalog

_register_catalog()


@hooks.register("register_admin_urls")
def register_application_admin_urls():
    from app_catalog.wagtail_admin.views import application_instance_cancel
    return [
        path("applications/<uuid:pk>/cancel/", application_instance_cancel, name="app_catalog_application_instance_cancel"),
    ]


@hooks.register("register_snippet_listing_buttons")
def application_instance_listing_buttons(snippet, user, next_url=None):
    if not isinstance(snippet, ApplicationInstance):
        return
    if not getattr(user, "is_staff", False):
        return
    if not (getattr(user, "is_superuser", False) or user.has_perm("app_catalog.change_applicationinstance")):
        return
    if snippet.status not in {ApplicationStatus.PENDING, ApplicationStatus.DEPLOYING}:
        return
    query = urlencode({"next": next_url}) if next_url else ""
    suffix = f"?{query}" if query else ""
    yield wagtailsnippets_widgets.SnippetListingButton(
        "Cancel installation",
        reverse("app_catalog_application_instance_cancel", kwargs={"pk": snippet.pk}) + suffix,
        priority=10,
    )
