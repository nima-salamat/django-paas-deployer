"""Wagtail hooks: register messenger models and cache administration."""
from __future__ import annotations

from django.urls import path
from wagtail import hooks

from messenger.wagtail_admin import register as _register_messenger

_register_messenger()


@hooks.register("register_admin_urls")
def register_messenger_admin_urls():
    from .views_admin import cache_dashboard

    return [
        path("messenger/cache/", cache_dashboard, name="wagtail_messenger_cache_dashboard"),
    ]

