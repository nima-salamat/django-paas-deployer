"""Wagtail hooks: register deploy models in Wagtail admin."""
from __future__ import annotations

from deploy.wagtail_admin import register as _register_deploy

_register_deploy()

from django.urls import path, reverse
from django.utils.http import urlencode
from wagtail import hooks
from wagtail.snippets import widgets as wagtailsnippets_widgets

from deploy.models import BaseRuntimeImage


@hooks.register("register_admin_urls")
def register_base_runtime_image_control_urls():
    from deploy.wagtail_admin.views import base_runtime_image_control

    return [
        path(
            "base-runtime-images/<uuid:pk>/<str:operation>/",
            base_runtime_image_control,
            name="deploy_base_runtime_image_control",
        ),
    ]


@hooks.register("register_snippet_listing_buttons")
def base_runtime_image_listing_buttons(snippet, user, next_url=None):
    if not isinstance(snippet, BaseRuntimeImage):
        return
    if not getattr(user, "is_staff", False):
        return
    if not (getattr(user, "is_superuser", False) or user.has_perm("deploy.change_baseruntimeimage")):
        return
    if str(getattr(snippet, "logical_runtime", "")).lower() == "php" and str(getattr(snippet, "variant", "")).lower() in {"apache-root", "apache-public"}:
        return

    query = urlencode({"next": next_url}) if next_url else ""
    suffix = f"?{query}" if query else ""
    yield wagtailsnippets_widgets.SnippetListingButton(
        "Build / Ensure available",
        reverse("deploy_base_runtime_image_control", kwargs={"pk": snippet.pk, "operation": "build"}) + suffix,
        priority=20,
    )
    yield wagtailsnippets_widgets.SnippetListingButton(
        "Renew / Rebuild",
        reverse("deploy_base_runtime_image_control", kwargs={"pk": snippet.pk, "operation": "renew"}) + suffix,
        priority=30,
    )
