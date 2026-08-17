"""Wagtail hooks: register messenger models and cache administration."""
from __future__ import annotations

from django.urls import path, reverse_lazy
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import MenuItem

from messenger.wagtail_admin import register as _register_messenger

_register_messenger()


@hooks.register("register_admin_urls")
def register_messenger_admin_urls():
    from .views_admin import cache_dashboard

    return [
        path("messenger/cache/", cache_dashboard, name="wagtail_messenger_cache_dashboard"),
    ]


@hooks.register("register_admin_menu_item")
def register_messenger_cache_menu_item():
    # Keep the cache entry adjacent to the Messenger snippet group in the
    # sidebar so administrators can treat it as a Messenger subsystem.
    return MenuItem(
        _("Messenger Cache"),
        reverse_lazy("wagtail_messenger_cache_dashboard"),
        icon_name="cog",
        order=219,
    )
