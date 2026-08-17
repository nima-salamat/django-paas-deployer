"""Custom Wagtail admin views: App Cache dashboard + system metrics API."""
from __future__ import annotations

from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods


def _is_staff(user):
    return bool(user and user.is_authenticated and user.is_staff)


@user_passes_test(_is_staff)
@require_http_methods(["GET", "POST"])
def cache_dashboard(request):
    from core.app_cache import (
        delete_cache_keys,
        get_app_cache_overview,
        get_cache_key_preview,
        invalidate_namespace,
        scan_app_cache_keys,
    )

    if request.method == "POST":
        action = request.POST.get("action") or ""
        if action == "flush":
            ns = request.POST.get("ns") or "all"
            invalidate_namespace(ns)
            return redirect(reverse("wagtail_core_cache_dashboard") + f"?flushed={ns}")
        if action == "delete_key":
            key = (request.POST.get("key") or "").strip()
            if key:
                delete_cache_keys(key)
            pattern = request.GET.get("pattern") or request.POST.get("pattern") or ""
            limit = request.GET.get("limit") or request.POST.get("limit") or "80"
            q = f"?pattern={pattern}&limit={limit}" if pattern else ""
            return redirect(reverse("wagtail_core_cache_dashboard") + q)

    pattern = request.GET.get("pattern") or ""
    try:
        limit = min(500, max(1, int(request.GET.get("limit") or 80)))
    except ValueError:
        limit = 80
    keys = scan_app_cache_keys(pattern, limit) if pattern else []
    preview_key = (request.GET.get("preview") or "").strip()
    preview = get_cache_key_preview(preview_key) if preview_key else None
    flushed = request.GET.get("flushed") or ""

    return render(
        request,
        "core/wagtail/cache_dashboard.html",
        {
            "title": "App Cache",
            "overview": get_app_cache_overview(),
            "pattern": pattern,
            "limit": limit,
            "keys": keys,
            "preview": preview,
            "flushed": flushed,
        },
    )


@user_passes_test(_is_staff)
@require_GET
def system_metrics_api(request):
    from core.system_metrics import get_system_metrics

    data = get_system_metrics()
    return JsonResponse(data)
