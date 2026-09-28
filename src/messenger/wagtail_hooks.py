"""Wagtail hooks for messenger operational cache administration only.

Conversation/message/call records have per-user and per-participant visibility
rules. They are intentionally not registered as Wagtail snippets; Django admin
remains the canonical staff moderation surface and the Wagtail cache dashboard
remains available through the separate admin URL below.
"""
from __future__ import annotations

from django.urls import path
from wagtail import hooks


@hooks.register("register_admin_urls")
def register_messenger_admin_urls():
    from .views_admin import cache_dashboard

    return [
        path("messenger/cache/", cache_dashboard, name="wagtail_messenger_cache_dashboard"),
    ]
