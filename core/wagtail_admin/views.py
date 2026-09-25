"""Wagtail cache administration: policy, namespaces, keys, and Messenger hot-cache."""
from __future__ import annotations

from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods


CACHE_POLICY = (
    ("service_user_ttl", "cache.service_user_ttl", "Service lists for users", 3600, 0, 604800),
    ("service_admin_ttl", "cache.service_admin_ttl", "Service lists for admins", 3600, 0, 604800),
    ("plan_ttl", "cache.plan_ttl", "Plan responses", 86400, 0, 604800),
    ("ticket_user_ttl", "cache.ticket_user_ttl", "Ticket lists for users", 3600, 0, 604800),
    ("ticket_admin_ttl", "cache.ticket_admin_ttl", "Ticket lists for admins", 3600, 0, 604800),
    ("user_admin_ttl", "cache.user_admin_ttl", "User admin lists", 3600, 0, 604800),
    ("message_size", "cache.message_size", "Messages kept per conversation", 1000, 100, 10000),
    ("message_ttl", "cache.message_ttl", "Messenger message windows", 21600, 0, 604800),
    ("messenger_list_ttl", "cache.messenger_list_ttl", "Messenger conversation lists", 300, 0, 86400),
    ("messenger_conv_ttl", "cache.messenger_conv_ttl", "Messenger conversation metadata", 120, 0, 86400),
)


def _is_staff(user):
    return bool(user and user.is_authenticated and user.is_staff)


def _policy_values():
    from core.app_cache import get_cache_ttl
    values = {}
    for form_key, setting_key, _label, default, minimum, maximum in CACHE_POLICY:
        cache_name = setting_key.removeprefix("cache.").removesuffix("_ttl")
        value = get_cache_ttl(cache_name)
        values[form_key] = max(minimum, min(value, maximum))
    return values


def _save_policy(post_data, actor):
    from core.settings_service import set_setting
    errors = []
    for form_key, setting_key, label, default, minimum, maximum in CACHE_POLICY:
        raw = str(post_data.get(form_key, "")).strip()
        try:
            value = int(raw)
        except (TypeError, ValueError):
            errors.append(f"{label}: enter a whole number.")
            continue
        if value < minimum or value > maximum:
            errors.append(f"{label}: value must be between {minimum} and {maximum}.")
            continue
        if not set_setting(setting_key, value, actor=actor):
            errors.append(f"{label}: setting could not be saved.")
    return errors


@user_passes_test(_is_staff)
@require_http_methods(["GET", "POST"])
def cache_dashboard(request):
    from core.app_cache import (
        delete_cache_keys,
        get_app_cache_overview,
        get_cache_key_preview,
        get_cache_ttl,
        invalidate_namespace,
        scan_app_cache_keys,
    )
    from messenger.message_cache import (
        get_cache_stats,
        inspect_conversation_cache,
        invalidate_all_cache,
        MessageCacheService,
        reset_cache_stats,
        search_cache_keys,
    )

    if request.method == "POST":
        action = request.POST.get("action") or ""

        if action == "save_policy":
            errors = _save_policy(request.POST, getattr(request.user, "username", None))
            query = "saved=1" if not errors else "policy_error=1"
            return redirect(reverse("wagtail_core_cache_dashboard") + f"?{query}")

        if action == "flush":
            ns = request.POST.get("ns") or "all"
            if ns == "all":
                deleted = 0
                for namespace in ("svc", "plan", "tkt", "usr"):
                    invalidate_namespace(namespace)
                deleted += invalidate_all_cache(reset_stats=False)
                return redirect(
                    reverse("wagtail_core_cache_dashboard")
                    + f"?flushed=all&deleted={deleted}"
                )
            if ns == "messenger":
                deleted = invalidate_all_cache(reset_stats=False)
            else:
                invalidate_namespace(ns)
                deleted = 0
            return redirect(
                reverse("wagtail_core_cache_dashboard")
                + f"?flushed={ns}&deleted={deleted}"
            )

        if action == "reset_stats":
            reset_cache_stats()
            return redirect(reverse("wagtail_core_cache_dashboard") + "?stats_reset=1")

        if action == "rebuild_conversation":
            raw = request.POST.get("conversation_id") or ""
            if raw.isdigit() and int(raw) > 0:
                MessageCacheService.rebuild_chat_cache(int(raw))
            return redirect(
                reverse("wagtail_core_cache_dashboard")
                + f"?conversation_id={raw}&conversation_action=rebuilt"
            )

        if action == "invalidate_conversation":
            raw = request.POST.get("conversation_id") or ""
            if raw.isdigit() and int(raw) > 0:
                MessageCacheService.invalidate_chat_cache(int(raw))
            return redirect(
                reverse("wagtail_core_cache_dashboard")
                + f"?conversation_id={raw}&conversation_action=invalidated"
            )

        if action == "delete_key":
            key = (request.POST.get("key") or "").strip()
            if key:
                delete_cache_keys(key)
            pattern = request.POST.get("pattern") or ""
            limit = request.POST.get("limit") or "80"
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

    conversation_raw = (request.GET.get("conversation_id") or "").strip()
    conversation_id = int(conversation_raw) if conversation_raw.isdigit() else None
    conversation = inspect_conversation_cache(conversation_id) if conversation_id else None

    messenger = get_cache_stats()
    total_msg = messenger["msg_hit"] + messenger["msg_miss"]
    total_list = messenger["list_hit"] + messenger["list_miss"]

    policy = _policy_values()

    return render(
        request,
        "core/wagtail/cache_dashboard.html",
        {
            "title": "Cache",
            "overview": get_app_cache_overview(),
            "messenger": messenger,
            "msg_hit_rate": round(messenger["msg_hit"] * 100 / total_msg, 1) if total_msg else 0,
            "list_hit_rate": round(messenger["list_hit"] * 100 / total_list, 1) if total_list else 0,
            "policy": policy,
            "pattern": pattern,
            "limit": limit,
            "keys": keys,
            "preview": preview,
            "conversation_id": conversation_id,
            "conversation": conversation,
            "flushed": request.GET.get("flushed") or "",
            "deleted": request.GET.get("deleted") or "0",
            "saved": request.GET.get("saved") == "1",
            "policy_error": request.GET.get("policy_error") == "1",
            "stats_reset": request.GET.get("stats_reset") == "1",
            "conversation_action": request.GET.get("conversation_action") or "",
            "policy_fields": [
                (*item, policy[item[0]]) for item in CACHE_POLICY
            ],
        },
    )


@user_passes_test(_is_staff)
@require_GET
def system_metrics_api(request):
    from core.system_metrics import get_system_metrics

    return JsonResponse(get_system_metrics())
