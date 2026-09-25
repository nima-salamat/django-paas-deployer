"""Legacy Messenger cache URL.

The cache controls now live in the unified Wagtail Cache screen under core.
This module remains only as a compatibility redirect for old bookmarks.
"""
from __future__ import annotations

from django.shortcuts import redirect


def cache_dashboard(request):
    return redirect("wagtail_core_cache_dashboard")
