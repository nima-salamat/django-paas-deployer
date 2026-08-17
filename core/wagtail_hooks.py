"""Wagtail hooks: core snippets + Cache menu + home system gauges."""
from __future__ import annotations

from django.urls import path, reverse_lazy
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import MenuItem

from core.wagtail_admin import register as _register_core

_register_core()


@hooks.register("register_admin_urls")
def register_core_admin_urls():
    from core.wagtail_admin.views import cache_dashboard, system_metrics_api

    return [
        path(
            "system/cache/",
            cache_dashboard,
            name="wagtail_core_cache_dashboard",
        ),
        path(
            "system/metrics/",
            system_metrics_api,
            name="wagtail_core_system_metrics",
        ),
    ]


@hooks.register("register_admin_menu_item")
def register_cache_menu_item():
    return MenuItem(
        _("Cache"),
        reverse_lazy("wagtail_core_cache_dashboard"),
        icon_name="cog",
        order=115,
    )


@hooks.register("construct_homepage_panels")
def add_system_gauges_panel(request, panels):
    from core.wagtail_admin.panels import SystemGaugesPanel

    # Only show for staff (everyone in Wagtail admin is staff, but be safe)
    if request.user.is_staff:
        panels.append(SystemGaugesPanel())
