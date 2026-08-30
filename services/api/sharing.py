"""
Service sharing API: share services into messenger groups or with individual users,
with fine-grained permission rules and activity events.
"""
from __future__ import annotations

import logging
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from ..models import Service, ServiceShare, ServiceShareEvent
from ..serializers import (
    DEFAULT_SHARE_RULES,
    ServiceShareSerializer,
    ServiceShareCreateSerializer,
    ServiceShareUpdateSerializer,
    ServiceShareEventSerializer,
    GetServiceSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_display(user) -> str:
    if not user:
        return "System"
    return getattr(user, "username", None) or getattr(user, "email", None) or str(user.pk)


def _get_active_share_for_user(service: Service, user) -> ServiceShare | None:
    """
    Return the active ServiceShare that grants *user* access to *service*,
    or None. Owner is never returned here (owner has full access via ownership).
    """
    if str(service.user_id) == str(user.id):
        return None  # owner path

    # Direct user share
    share = (
        ServiceShare.objects.filter(
            service=service,
            target_user=user,
            is_active=True,
        )
        .select_related("service", "shared_by", "group", "target_user")
        .first()
    )
    if share:
        return share

    # Group shares: user must be an *active* participant (not left/kicked)
    from services.share_cleanup import active_group_ids_for_user, user_is_active_group_member

    group_ids = active_group_ids_for_user(user)
    if not group_ids:
        return None

    share = (
        ServiceShare.objects.filter(
            service=service,
            group_id__in=group_ids,
            is_active=True,
        )
        .select_related("service", "shared_by", "group", "target_user")
        .first()
    )
    if not share:
        return None
    # Double-check sharer is still an active member of the group
    if share.group_id and not user_is_active_group_member(share.shared_by, share.group_id):
        # Stale share — deactivate lazily
        try:
            from services.share_cleanup import deactivate_shares_created_by_user_in_group
            deactivate_shares_created_by_user_in_group(
                share.shared_by_id, share.group_id, reason="sharer_not_in_group"
            )
        except Exception:
            pass
        return None
    return share


def user_can_access_service(service: Service, user, action: str = "can_view") -> tuple[bool, ServiceShare | None]:
    """
    Returns (allowed, share_or_None).
    Owner always allowed for any action.
    """
    if str(service.user_id) == str(user.id):
        return True, None

    share = _get_active_share_for_user(service, user)
    if not share:
        return False, None

    # Expiry
    if getattr(share, "expires_at", None) is not None:
        from django.utils import timezone
        if share.expires_at <= timezone.now():
            try:
                share.is_active = False
                share.save(update_fields=["is_active", "updated_at"])
            except Exception:
                pass
            return False, None

    # Admin-only group shares
    if getattr(share, "admin_only", False) and share.group_id:
        from services.share_permissions import user_is_group_admin
        if not user_is_group_admin(user, share.group_id):
            # Still allow pure view listing if can_view — product choice: deny all acts
            if action != "can_view":
                return False, share
            # view allowed for members to see the service exists
            return True, share

    # Per-member override (group shares)
    member_rules = None
    if share.group_id:
        try:
            from services.models import ServiceShareMember
            mem = ServiceShareMember.objects.filter(share=share, user=user).first()
            if mem is not None:
                if not mem.is_enabled:
                    return False, share
                member_rules = mem.rules
        except Exception:
            member_rules = None

    if action == "can_view":
        if member_rules is not None:
            from services.share_permissions import normalize_rules
            return bool(normalize_rules(member_rules).get("can_view", True)), share
        return True, share

    if member_rules is not None:
        from services.share_permissions import normalize_rules
        return bool(normalize_rules(member_rules).get(action, False)), share
    return share.allows(action), share


def record_share_event(
    share: ServiceShare,
    actor,
    action: str,
    message: str = "",
    metadata: dict | None = None,
) -> ServiceShareEvent:
    """Persist event and (if group share) post a system message into the group."""
    event = ServiceShareEvent.objects.create(
        share=share,
        actor=actor,
        action=action,
        message=message or "",
        metadata=metadata or {},
    )
    if share.group_id:
        try:
            _post_system_message_to_group(share, actor, action, message or event.message)
        except Exception:
            logger.exception(
                "Failed to post system message for share event share=%s action=%s",
                share.pk,
                action,
            )
    return event


def _post_system_message_to_group(
    share: ServiceShare,
    actor,
    action: str,
    message: str,
) -> None:
    """
    Post a system message into the group.

    Body format (machine-readable prefix for the UI):
      __service_event__:{json}\n{human readable label}

    json keys: action, service_id, service_name, share_id, actor_id, actor_name
    """
    import json as _json
    from messenger.models import Message, Conversation

    conv = share.group
    if not conv or conv.type != Conversation.Type.GROUP:
        return

    actor_name = _user_display(actor)
    service_name = getattr(share.service, "name", str(share.service_id))
    action_labels = {
        "share": f"{actor_name} shared service «{service_name}» with this group.",
        "unshare": f"{actor_name} stopped sharing service «{service_name}».",
        "start": f"{actor_name} started service «{service_name}».",
        "stop": f"{actor_name} stopped service «{service_name}».",
        "restart": f"{actor_name} restarted service «{service_name}».",
        "deploy": f"{actor_name} deployed / rebuilt service «{service_name}».",
        "rules_updated": f"{actor_name} updated permission rules for «{service_name}».",
    }
    human = message or action_labels.get(
        action, f"{actor_name} performed «{action}» on «{service_name}»."
    )
    payload = {
        "action": action,
        "service_id": str(share.service_id),
        "service_name": service_name,
        "share_id": str(share.pk),
        "actor_id": str(getattr(actor, "id", "") or ""),
        "actor_name": actor_name,
    }
    body = f"__service_event__:{_json.dumps(payload, ensure_ascii=False)}\n{human}"

    msg = Message.objects.create(
        conversation=conv,
        sender=None,  # system
        body=body,
        is_system=True,
    )
    try:
        from messenger.consumers import broadcast_message
        broadcast_message(msg)
    except Exception:
        logger.exception("broadcast_message failed for service share event")
    try:
        from messenger.message_cache import schedule_add_message
        schedule_add_message(msg)
    except Exception:
        pass


def _service_qs_for_user_including_shared(user):
    """Own services + services shared with user (direct or via groups)."""
    from messenger.models import ConversationParticipant

    group_ids = list(
        ConversationParticipant.objects.filter(user=user, left_at__isnull=True).values_list(
            "conversation_id", flat=True
        )
    )
    shared_service_ids = ServiceShare.objects.filter(
        is_active=True,
    ).filter(
        Q(target_user=user) | Q(group_id__in=group_ids)
    ).values_list("service_id", flat=True)

    return Service.objects.filter(
        Q(user=user) | Q(id__in=shared_service_ids)
    ).select_related("user", "network", "plan", "selected_deploy").distinct()


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def list_my_services(request):
    """Only services owned by the current user."""
    qs = Service.objects.filter(user=request.user).select_related(
        "user", "network", "plan", "selected_deploy"
    )
    data = GetServiceSerializer(qs, many=True, context={"request": request}).data
    return Response({"result": "success", "services": data, "scope": "mine"})


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def list_shared_services(request):
    """
    Services that are shared *with me* (I am not the owner), plus
    services that *I* have shared (so I can manage them).
    Query params:
      - scope: received | created | all  (default all)
    """
    scope = (request.query_params.get("scope") or "all").strip().lower()
    from messenger.models import ConversationParticipant

    group_ids = list(
        ConversationParticipant.objects.filter(user=request.user, left_at__isnull=True).values_list(
            "conversation_id", flat=True
        )
    )

    qs = ServiceShare.objects.filter(is_active=True).select_related(
        "service", "service__user", "service__plan", "shared_by", "group", "target_user"
    )

    if scope == "received":
        qs = qs.filter(Q(target_user=request.user) | Q(group_id__in=group_ids)).exclude(
            shared_by=request.user
        )
    elif scope == "created":
        qs = qs.filter(shared_by=request.user)
    else:
        qs = qs.filter(
            Q(shared_by=request.user)
            | Q(target_user=request.user)
            | Q(group_id__in=group_ids)
        )

    data = ServiceShareSerializer(qs, many=True, context={"request": request}).data
    return Response({"result": "success", "shares": data, "scope": scope})


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def create_share(request):
    """
    Share one of *my* services with a group or a user.
    Body: service_id, group_id | target_user_id, rules?, note?
    """
    ser = ServiceShareCreateSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data

    service = get_object_or_404(Service, pk=data["service_id"], user=request.user)

    group = None
    target_user = None
    if data.get("group_id"):
        from messenger.models import Conversation, ConversationParticipant

        group = get_object_or_404(
            Conversation, pk=data["group_id"], type=Conversation.Type.GROUP
        )
        # Must be a participant (preferably admin/owner, but allow any member for now)
        if not ConversationParticipant.objects.filter(
            conversation=group, user=request.user, left_at__isnull=True
        ).exists():
            return Response(
                {"result": "error", "detail": _("You are not a member of this group.")},
                status=status.HTTP_403_FORBIDDEN,
            )
    else:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        target_user = get_object_or_404(User, pk=data["target_user_id"])
        if str(target_user.id) == str(request.user.id):
            return Response(
                {"result": "error", "detail": _("Cannot share a service with yourself.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Prevent duplicate active share to same target
    dup_q = Q(service=service, is_active=True)
    if group:
        dup_q &= Q(group=group)
    else:
        dup_q &= Q(target_user=target_user)
    if ServiceShare.objects.filter(dup_q).exists():
        return Response(
            {"result": "error", "detail": _("This service is already shared with that target.")},
            status=status.HTTP_409_CONFLICT,
        )

    with transaction.atomic():
        share = ServiceShare(
            service=service,
            group=group,
            target_user=target_user,
            shared_by=request.user,
            rules=data.get("rules") or dict(DEFAULT_SHARE_RULES),
            note=data.get("note") or "",
            is_active=True,
            expires_at=data.get("expires_at"),
            admin_only=bool(data.get("admin_only") or False),
            preset=(data.get("preset") or "")[:32],
        )
        share.save()
        # Optional per-member rules at create time (ignore if table not migrated)
        members_payload = request.data.get("members")
        if group and isinstance(members_payload, list):
            try:
                from services.models import ServiceShareMember
                from services.share_permissions import normalize_rules
                from messenger.models import ConversationParticipant
                valid_ids = {
                    str(x)
                    for x in ConversationParticipant.objects.filter(
                        conversation=group, left_at__isnull=True
                    ).values_list("user_id", flat=True)
                }
                default_rules = normalize_rules(share.rules)
                for item in members_payload:
                    if not isinstance(item, dict):
                        continue
                    uid = item.get("user_id")
                    if str(uid) not in valid_ids:
                        continue
                    rules = normalize_rules(item.get("rules") or {})
                    is_enabled = bool(item.get("is_enabled", True))
                    if is_enabled and rules == default_rules:
                        continue
                    ServiceShareMember.objects.create(
                        share=share,
                        user_id=uid,
                        rules=rules,
                        is_enabled=is_enabled,
                    )
            except Exception:
                logger.exception("create_share: member rules skipped")
        try:
            record_share_event(
                share,
                actor=request.user,
                action="share",
                message="",
                metadata={"rules": share.rules},
            )
        except Exception:
            logger.exception("create_share: record_share_event failed")

    try:
        share = (
            ServiceShare.objects.select_related(
                "service", "shared_by", "group", "target_user"
            ).get(pk=share.pk)
        )
        out = ServiceShareSerializer(share, context={"request": request}).data
    except Exception:
        logger.exception("create_share: serialize failed")
        out = {
            "id": str(share.pk),
            "service_id": str(share.service_id),
            "group_id": share.group_id,
            "target_user_id": str(share.target_user_id) if share.target_user_id else None,
            "is_active": share.is_active,
        }
    return Response({"result": "success", "share": out}, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def share_detail(request, pk):
    """
    GET    – detail + my_permissions
    PATCH  – update rules / note / is_active (owner only)
    DELETE – deactivate (unshare) (owner only)
    """
    share = get_object_or_404(
        ServiceShare.objects.select_related(
            "service", "shared_by", "group", "target_user"
        ),
        pk=pk,
    )

    is_owner = str(share.shared_by_id) == str(request.user.id)

    # Non-owners may only GET if they are recipients
    if request.method == "GET":
        if not is_owner:
            allowed, _ = user_can_access_service(share.service, request.user, "can_view")
            if not allowed:
                return Response(
                    {"result": "error", "detail": _("Not found or access denied.")},
                    status=status.HTTP_404_NOT_FOUND,
                )
        data = ServiceShareSerializer(share, context={"request": request}).data
        return Response({"result": "success", "share": data})

    if not is_owner:
        return Response(
            {"result": "error", "detail": _("Only the owner can modify this share.")},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "DELETE":
        share.is_active = False
        share.save(update_fields=["is_active", "updated_at"])
        record_share_event(share, actor=request.user, action="unshare")
        return Response({"result": "success", "detail": _("Share deactivated.")})

    # PATCH
    ser = ServiceShareUpdateSerializer(data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data
    changed = []
    if "rules" in data:
        share.rules = data["rules"]
        changed.append("rules")
    if "note" in data:
        share.note = data["note"]
        changed.append("note")
    if "is_active" in data:
        share.is_active = data["is_active"]
        changed.append("is_active")
    if "expires_at" in data:
        share.expires_at = data["expires_at"]
        changed.append("expires_at")
    if "admin_only" in data:
        share.admin_only = data["admin_only"]
        changed.append("admin_only")
    if "preset" in data:
        preset = (data.get("preset") or "").strip().lower()
        if preset:
            from services.share_permissions import RULE_PRESETS
            if preset in RULE_PRESETS:
                share.rules = dict(RULE_PRESETS[preset])
                share.preset = preset
                changed.append("preset")
                changed.append("rules")
        else:
            share.preset = ""
            changed.append("preset")
    if changed:
        share.save()
        action = "unshare" if ("is_active" in data and not data["is_active"]) else "rules_updated"
        record_share_event(
            share,
            actor=request.user,
            action=action,
            metadata={"changed": changed, "rules": share.rules},
        )

    out = ServiceShareSerializer(share, context={"request": request}).data
    return Response({"result": "success", "share": out})


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def share_permissions(request, pk):
    """
    Return the effective permission JSON for the current user on this share.
    UI uses this to enable/disable buttons.
    """
    share = get_object_or_404(ServiceShare, pk=pk, is_active=True)
    is_owner = str(share.shared_by_id) == str(request.user.id)
    if is_owner:
        perms = {k: True for k in DEFAULT_SHARE_RULES}
    else:
        allowed, s = user_can_access_service(share.service, request.user, "can_view")
        if not allowed or s is None:
            return Response(
                {"result": "error", "detail": _("Access denied.")},
                status=status.HTTP_403_FORBIDDEN,
            )
        perms = dict(s.rules or DEFAULT_SHARE_RULES)

    return Response(
        {
            "result": "success",
            "permissions": perms,
            "is_owner": is_owner,
            "known_actions": list(DEFAULT_SHARE_RULES.keys()),
            "labels": __import__("services.share_permissions", fromlist=["RULE_LABELS"]).RULE_LABELS,
            "defaults": __import__("services.share_permissions", fromlist=["DEFAULT_SHARE_RULES"]).DEFAULT_SHARE_RULES,
        }
    )


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def share_events(request, pk):
    """List activity events for a share (owner or recipient with can_view)."""
    share = get_object_or_404(ServiceShare, pk=pk)
    is_owner = str(share.shared_by_id) == str(request.user.id)
    if not is_owner:
        allowed, _ = user_can_access_service(share.service, request.user, "can_view")
        if not allowed:
            return Response(
                {"result": "error", "detail": _("Access denied.")},
                status=status.HTTP_403_FORBIDDEN,
            )
    events = share.events.select_related("actor").all()[:100]
    data = ServiceShareEventSerializer(events, many=True).data
    return Response({"result": "success", "events": data})


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def list_services_unified(request):
    """
    Unified list for the Services page:
      - mine: owned by me
      - shared: shared with me (received)
    Returns both lists so UI can show tabs.
    """
    mine = Service.objects.filter(user=request.user).select_related(
        "user", "network", "plan", "selected_deploy"
    )
    mine_data = GetServiceSerializer(mine, many=True, context={"request": request}).data

    from messenger.models import ConversationParticipant

    group_ids = list(
        ConversationParticipant.objects.filter(user=request.user, left_at__isnull=True).values_list(
            "conversation_id", flat=True
        )
    )
    received = (
        ServiceShare.objects.filter(is_active=True)
        .filter(Q(target_user=request.user) | Q(group_id__in=group_ids))
        .exclude(shared_by=request.user)
        .select_related(
            "service", "service__user", "service__plan", "shared_by", "group", "target_user"
        )
    )
    received_data = ServiceShareSerializer(
        received, many=True, context={"request": request}
    ).data

    created = (
        ServiceShare.objects.filter(is_active=True, shared_by=request.user)
        .select_related(
            "service", "service__user", "service__plan", "shared_by", "group", "target_user"
        )
    )
    created_data = ServiceShareSerializer(
        created, many=True, context={"request": request}
    ).data

    return Response(
        {
            "result": "success",
            "mine": mine_data,
            "shared_with_me": received_data,
            "shared_by_me": created_data,
        }
    )


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def shares_for_group(request, group_id):
    """
    List active service shares for a messenger group.
    Caller must be a participant of the group.
    """
    from messenger.models import Conversation, ConversationParticipant

    conv = get_object_or_404(Conversation, pk=group_id, type=Conversation.Type.GROUP)
    if not ConversationParticipant.objects.filter(conversation=conv, user=request.user, left_at__isnull=True).exists():
        return Response(
            {"result": "error", "detail": _("You are not a member of this group.")},
            status=status.HTTP_403_FORBIDDEN,
        )
    qs = (
        ServiceShare.objects.filter(group=conv, is_active=True)
        .select_related("service", "service__user", "service__plan", "shared_by", "group", "target_user")
        .order_by("-created_at")
    )
    try:
        data = ServiceShareSerializer(qs, many=True, context={"request": request}).data
    except Exception:
        logger.exception("shares_for_group serialize failed")
        data = [
            {
                "id": str(s.pk),
                "service_id": str(s.service_id),
                "service_name": getattr(getattr(s, "service", None), "name", None),
                "group_id": s.group_id,
                "shared_by_id": str(s.shared_by_id),
                "is_active": s.is_active,
                "rules": s.rules or {},
            }
            for s in qs
        ]
    return Response({"result": "success", "shares": data, "group_id": conv.pk})


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def leave_share(request, pk):
    """
    Recipient rejects / leaves a share (does not delete owner's other shares).
    For group shares, leaving the messenger group is the primary path; this
    endpoint is mainly for direct user-shares, or to hide a group share from self
    by deactivating only if target_user == request.user.
    """
    share = get_object_or_404(ServiceShare, pk=pk, is_active=True)
    is_direct = share.target_user_id and str(share.target_user_id) == str(request.user.id)
    if not is_direct:
        return Response(
            {
                "result": "error",
                "detail": _(
                    "For group shares, leave the messenger group to revoke your access. "
                    "Only direct user-shares can be left here."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    share.is_active = False
    share.save(update_fields=["is_active", "updated_at"])
    record_share_event(
        share,
        actor=request.user,
        action="unshare",
        message="Recipient left the share.",
        metadata={"reason": "recipient_left"},
    )
    return Response({"result": "success", "detail": _("You left this share.")})


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def share_presets(request):
    from services.share_permissions import RULE_PRESETS, RULE_LABELS, DEFAULT_SHARE_RULES
    return Response(
        {
            "result": "success",
            "presets": RULE_PRESETS,
            "labels": RULE_LABELS,
            "defaults": DEFAULT_SHARE_RULES,
        }
    )


@api_view(["GET", "PUT"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def share_members(request, pk):
    """
    GET  — list group members with effective rules for this share.
    PUT  — replace per-member overrides.
           body: { "members": [ { "user_id": 1, "rules": {...}, "is_enabled": true }, ... ] }
    Only the share owner (shared_by) may write.
    """
    from services.models import ServiceShareMember
    from services.share_permissions import normalize_rules, DEFAULT_SHARE_RULES
    from messenger.models import ConversationParticipant

    share = get_object_or_404(
        ServiceShare.objects.select_related("group", "service", "shared_by"),
        pk=pk,
        is_active=True,
    )
    if not share.group_id:
        return Response(
            {"result": "error", "detail": _("Member rules only apply to group shares.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    is_owner = str(share.shared_by_id) == str(request.user.id)
    # Must be active group member to read
    if not ConversationParticipant.objects.filter(
        conversation_id=share.group_id, user=request.user, left_at__isnull=True
    ).exists() and not is_owner:
        return Response(
            {"result": "error", "detail": _("Not a member of this group.")},
            status=status.HTTP_403_FORBIDDEN,
        )

    participants = list(
        ConversationParticipant.objects.filter(
            conversation_id=share.group_id, left_at__isnull=True
        ).select_related("user")
    )
    overrides = {
        str(m.user_id): m
        for m in ServiceShareMember.objects.filter(share=share)
    }
    default_rules = normalize_rules(share.rules)

    if request.method == "GET":
        rows = []
        for p in participants:
            uid = str(p.user_id)
            ov = overrides.get(uid)
            if ov is not None:
                eff = normalize_rules(ov.rules) if ov.is_enabled else {k: False for k in DEFAULT_SHARE_RULES}
                enabled = ov.is_enabled
                has_override = True
            else:
                eff = default_rules
                enabled = True
                has_override = False
            u = p.user
            rows.append({
                "user_id": p.user_id,
                "username": getattr(u, "username", "") or "",
                "display_name": getattr(u, "get_full_name", lambda: "")() or getattr(u, "username", ""),
                "role": p.role,
                "is_enabled": enabled,
                "has_override": has_override,
                "rules": eff,
                "is_self": str(p.user_id) == str(request.user.id),
            })
        return Response({
            "result": "success",
            "share_id": str(share.pk),
            "default_rules": default_rules,
            "members": rows,
            "can_edit": is_owner,
        })

    # PUT
    if not is_owner:
        return Response(
            {"result": "error", "detail": _("Only the share owner can edit member rules.")},
            status=status.HTTP_403_FORBIDDEN,
        )
    members_payload = request.data.get("members")
    if not isinstance(members_payload, list):
        return Response(
            {"result": "error", "detail": _("members must be a list.")},
            status=status.HTTP_400_BAD_REQUEST,
        )
    valid_ids = {str(p.user_id) for p in participants}
    # Clear and re-apply overrides that differ from default OR is_enabled=False
    ServiceShareMember.objects.filter(share=share).delete()
    created = 0
    for item in members_payload:
        if not isinstance(item, dict):
            continue
        uid = str(item.get("user_id") or "")
        if uid not in valid_ids:
            continue
        # skip owner of service / share owner optional — allow still
        rules = normalize_rules(item.get("rules") or {})
        is_enabled = bool(item.get("is_enabled", True))
        # Only store row if disabled or rules differ from default
        if is_enabled and rules == default_rules:
            continue
        ServiceShareMember.objects.create(
            share=share,
            user_id=item.get("user_id"),
            rules=rules,
            is_enabled=is_enabled,
        )
        created += 1
    record_share_event(
        share,
        actor=request.user,
        action="rules_updated",
        message="Per-member rules updated.",
        metadata={"member_overrides": created},
    )
    return Response({"result": "success", "overrides": created})
