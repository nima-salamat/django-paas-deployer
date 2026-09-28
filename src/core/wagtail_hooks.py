"""Wagtail hooks for core operational administration.

Core deliberately does not auto-register Django models in Wagtail. Settings
remain Django-admin owned, while Wagtail contains only explicit operational
views such as the cache dashboard and system gauges.
"""
from __future__ import annotations

from django.urls import path, reverse_lazy
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import MenuItem


@hooks.register("register_admin_urls")
def register_core_admin_urls():
    from core.wagtail_admin.views import cache_dashboard, system_metrics_api

    return [
        path("system/cache/", cache_dashboard, name="wagtail_core_cache_dashboard"),
        path("system/metrics/", system_metrics_api, name="wagtail_core_system_metrics"),
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

    if request.user.is_staff:
        panels.append(SystemGaugesPanel())
