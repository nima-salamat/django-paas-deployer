"""Wagtail hooks: register deploy models and safe operator actions."""
from __future__ import annotations

from django.urls import path, reverse
from django.utils.http import urlencode
from wagtail import hooks
from wagtail.snippets import widgets as wagtailsnippets_widgets

from deploy.wagtail_admin import register as _register_deploy
from deploy.models import BaseRuntimeImage, Deploy

_register_deploy()


@hooks.register("register_admin_urls")
def register_base_runtime_image_control_urls():
    from deploy.wagtail_admin.views import base_runtime_image_control, deployment_cancel
    return [
        path("base-runtime-images/<uuid:pk>/<str:operation>/", base_runtime_image_control, name="deploy_base_runtime_image_control"),
        path("deployments/<uuid:pk>/cancel/", deployment_cancel, name="deploy_deployment_cancel"),
    ]


@hooks.register("before_delete_snippet")
def protect_base_runtime_image_delete(request, instances):
    """Do not delete a base-image registry row while it is actively needed."""
    from django.http import HttpResponseBadRequest

    base_rows = [item for item in instances if isinstance(item, BaseRuntimeImage)]
    blocked = []
    for row in base_rows:
        if row.status == BaseRuntimeImage.Status.BUILDING or row.build_task_id:
            blocked.append(f"{row.image_ref}: active build")
            continue
        if row.leases.filter(released_at__isnull=True).exists():
            blocked.append(f"{row.image_ref}: active deployment lease")
    if blocked:
        return HttpResponseBadRequest("Cannot delete active base runtime image rows: " + "; ".join(blocked))
    return None


@hooks.register("register_snippet_listing_buttons")
def base_runtime_image_listing_buttons(snippet, user, next_url=None):
    if isinstance(snippet, Deploy):
        if not getattr(user, "is_staff", False):
            return
        if not (getattr(user, "is_superuser", False) or user.has_perm("deploy.change_deploy")):
            return
        if str(getattr(snippet, "status", "")).lower() not in {"pending", "running", "rolling_back"}:
            return
        query = urlencode({"next": next_url}) if next_url else ""
        suffix = f"?{query}" if query else ""
        yield wagtailsnippets_widgets.SnippetListingButton(
            "Cancel deployment",
            reverse("deploy_deployment_cancel", kwargs={"pk": snippet.pk}) + suffix,
            priority=10,
        )
        return
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
