"""
Daily deploy / build quotas.

- Default: 50 deploy actions per user per service per calendar day (server TZ).
- Share recipients may have a lower (or equal) limit via rules["daily_deploy_limit"].
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

MAX_DEPLOYS_PER_DAY = 50


def _day_start():
    now = timezone.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def count_deploys_created_today(service_id, user_id) -> int:
    """Count Deploy rows created today for this service by this user."""
    from .models import Deploy

    start = _day_start()
    qs = Deploy.objects.filter(service_id=service_id, created_at__gte=start)
    # Prefer created_by; fall back to service owner for legacy rows without created_by
    qs = qs.filter(
        Q(created_by_id=user_id)
        | Q(created_by__isnull=True, service__user_id=user_id)
    )
    return qs.count()


def count_rebuild_events_today(service_id, user_id) -> int:
    """
    Count rebuild/deploy share events today (covers rebuild without new Deploy row).
    Best-effort; returns 0 if ServiceShareEvent unavailable.
    """
    try:
        from services.models import ServiceShareEvent

        start = _day_start()
        return ServiceShareEvent.objects.filter(
            share__service_id=service_id,
            actor_id=user_id,
            action__in=("deploy", "rebuild", "start"),
            created_at__gte=start,
        ).count()
    except Exception:
        return 0


def count_deploy_actions_today(service_id, user_id) -> int:
    """
    Combined activity: new Deploy uploads + rebuild-ish events.
    Uses max of the two sources to avoid under-counting without double-counting
    when both fire for the same action (create alone is enough for uploads).
    """
    created = count_deploys_created_today(service_id, user_id)
    # Rebuilds on existing deploy don't create a row — approximate via events
    events = count_rebuild_events_today(service_id, user_id)
    return max(created, events) if events > created else created + max(0, events - created)


def resolve_daily_limit_for_user(service, user) -> int:
    """
    Owner / staff: MAX_DEPLOYS_PER_DAY.
    Share recipient: min(MAX_DEPLOYS_PER_DAY, rules.daily_deploy_limit) when set;
    if daily_deploy_limit is 0 or missing, default to MAX_DEPLOYS_PER_DAY when can_deploy_add,
    else 0.
    """
    if user is None:
        return 0
    if str(getattr(service, "user_id", None)) == str(getattr(user, "id", None)):
        return MAX_DEPLOYS_PER_DAY
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return MAX_DEPLOYS_PER_DAY

    try:
        from services.api.sharing import user_can_access_service
        from services.share_permissions import normalize_rules

        allowed, share = user_can_access_service(service, user, "can_deploy_add")
        if not allowed and share is None:
            # try rebuild-only
            allowed_rb, share = user_can_access_service(service, user, "can_rebuild")
            if not allowed_rb:
                return 0
        if share is None:
            return MAX_DEPLOYS_PER_DAY

        rules = normalize_rules(share.rules or {})
        # member override
        try:
            from services.models import ServiceShareMember

            mem = ServiceShareMember.objects.filter(share=share, user=user).first()
            if mem is not None:
                if not mem.is_enabled:
                    return 0
                rules = normalize_rules(mem.rules or {})
        except Exception:
            pass

        raw = rules.get("daily_deploy_limit", None)
        if raw is not None and str(raw).strip() != "":
            try:
                n = int(raw)
                if n < 0:
                    n = 0
                return min(n, MAX_DEPLOYS_PER_DAY)
            except (TypeError, ValueError):
                pass
        # default for share members with deploy rights
        return MAX_DEPLOYS_PER_DAY
    except Exception:
        logger.exception("resolve_daily_limit_for_user failed")
        return MAX_DEPLOYS_PER_DAY


def assert_daily_deploy_allowed(service, user) -> tuple[bool, str, int, int]:
    """
    Returns (ok, message, used, limit).
    """
    limit = resolve_daily_limit_for_user(service, user)
    used = count_deploys_created_today(service.pk, user.id)
    # Also count rebuilds roughly
    try:
        used = count_deploy_actions_today(service.pk, user.id)
    except Exception:
        pass
    if limit <= 0:
        return False, str(_("Daily deploy limit is 0 for your account on this service.")), used, limit
    if used >= limit:
        return (
            False,
            str(
                _(
                    "Daily deploy limit reached (%(used)s/%(limit)s). Try again tomorrow."
                )
                % {"used": used, "limit": limit}
            ),
            used,
            limit,
        )
    return True, "", used, limit
