"""Wagtail admin view for the Messenger Redis hot-cache."""
from __future__ import annotations

from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods


def _is_staff(user):
    return bool(user and user.is_authenticated and user.is_staff)


@user_passes_test(_is_staff)
@require_http_methods(["GET", "POST"])
def cache_dashboard(request):
    from .message_cache import (
        get_cache_stats,
        inspect_conversation_cache,
        invalidate_all_cache,
        MessageCacheService,
        reset_cache_stats,
        search_cache_keys,
    )

    if request.method == "POST":
        action = request.POST.get("action") or ""
        if action == "reset_stats":
            reset_cache_stats()
            return redirect(reverse("wagtail_messenger_cache_dashboard") + "?status=stats-reset")
        if action == "flush_all":
            deleted = invalidate_all_cache(reset_stats=False)
            return redirect(reverse("wagtail_messenger_cache_dashboard") + f"?status=flushed&deleted={deleted}")
        if action == "rebuild":
            conv_id = int(request.POST.get("conv_id") or 0)
            if conv_id > 0:
                MessageCacheService.rebuild_chat_cache(conv_id)
            return redirect(reverse("wagtail_messenger_cache_dashboard") + f"?conv_id={conv_id}&status=rebuilt")
        if action == "invalidate":
            conv_id = int(request.POST.get("conv_id") or 0)
            if conv_id > 0:
                MessageCacheService.invalidate_chat_cache(conv_id)
            return redirect(reverse("wagtail_messenger_cache_dashboard") + f"?conv_id={conv_id}&status=invalidated")

    conv_id_raw = (request.GET.get("conv_id") or "").strip()
    conv_id = int(conv_id_raw) if conv_id_raw.isdigit() else None
    inspect = inspect_conversation_cache(conv_id) if conv_id else None
    pattern = request.GET.get("pattern") or ""
    try:
        limit = min(500, max(1, int(request.GET.get("limit") or 80)))
    except ValueError:
        limit = 80
    keys = search_cache_keys(pattern or "msgcache:*", limit) if pattern or request.GET.get("search") else []
    stats = get_cache_stats()
    msg_total = stats["msg_hit"] + stats["msg_miss"]
    list_total = stats["list_hit"] + stats["list_miss"]
    msg_hit_rate = round(stats["msg_hit"] * 100 / msg_total, 1) if msg_total else 0
    list_hit_rate = round(stats["list_hit"] * 100 / list_total, 1) if list_total else 0

    return render(
        request,
        "admin/messenger/cache_dashboard.html",
        {
            "title": "Messenger Cache",
            "stats": stats,
            "msg_hit_rate": msg_hit_rate,
            "list_hit_rate": list_hit_rate,
            "conv_id": conv_id,
            "inspect": inspect,
            "pattern": pattern,
            "limit": limit,
            "keys": keys,
            "status": request.GET.get("status") or "",
            "deleted": request.GET.get("deleted") or "0",
        },
    )
