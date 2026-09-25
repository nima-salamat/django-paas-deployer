"""
Lifecycle cleanup for ServiceShare when messenger membership changes.

Rules:
  - Group-based access is only valid while the actor is an *active*
    participant (left_at IS NULL).
  - When a user leaves / is removed from a group:
      * Any shares THEY created targeting that group are deactivated
        (sharing only makes sense while the sharer is in the group).
      * They lose recipient access automatically via membership checks
        (no need to delete other members' shares).
  - When a group is hard-deleted, ServiceShare rows CASCADE-delete via FK.
    We still best-effort deactivate first so events stay consistent.
"""
from __future__ import annotations

import logging
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


def active_participant_q(user=None, conversation_id=None):
    """Filter kwargs / Q for active (not left) participants."""
    q = Q(left_at__isnull=True)
    if user is not None:
        q &= Q(user=user)
    if conversation_id is not None:
        q &= Q(conversation_id=conversation_id)
    return q


def user_is_active_group_member(user, group_id) -> bool:
    from messenger.models import ConversationParticipant

    return ConversationParticipant.objects.filter(
        conversation_id=group_id,
        user=user,
        left_at__isnull=True,
    ).exists()


def active_group_ids_for_user(user) -> list:
    from messenger.models import ConversationParticipant

    return list(
        ConversationParticipant.objects.filter(
            user=user,
            left_at__isnull=True,
        ).values_list("conversation_id", flat=True)
    )


def deactivate_shares_created_by_user_in_group(user_id, group_id, *, reason: str = "left_group") -> int:
    """
    Deactivate all active group-shares that *user* created for *group*.
    Returns number of rows updated.
    """
    from .models import ServiceShare, ServiceShareEvent

    qs = ServiceShare.objects.filter(
        shared_by_id=user_id,
        group_id=group_id,
        is_active=True,
    )
    ids = list(qs.values_list("pk", flat=True))
    if not ids:
        return 0
    updated = qs.update(is_active=False, updated_at=timezone.now())
    # Audit events (bulk)
    for share_id in ids:
        try:
            ServiceShareEvent.objects.create(
                share_id=share_id,
                actor_id=user_id,
                action="unshare",
                message=f"Share auto-deactivated ({reason}).",
                metadata={"reason": reason, "group_id": str(group_id)},
            )
        except Exception:
            logger.exception("Failed to log auto-unshare for share=%s", share_id)
    logger.info(
        "Deactivated %s service share(s) for user=%s group=%s reason=%s",
        updated,
        user_id,
        group_id,
        reason,
    )
    return updated


def deactivate_all_shares_for_group(group_id, *, reason: str = "group_deleted") -> int:
    """Deactivate every active share targeting this group (before hard delete)."""
    from .models import ServiceShare, ServiceShareEvent

    qs = ServiceShare.objects.filter(group_id=group_id, is_active=True)
    ids = list(qs.values_list("pk", flat=True))
    if not ids:
        return 0
    updated = qs.update(is_active=False, updated_at=timezone.now())
    for share_id in ids:
        try:
            ServiceShareEvent.objects.create(
                share_id=share_id,
                actor=None,
                action="unshare",
                message=f"Share auto-deactivated ({reason}).",
                metadata={"reason": reason, "group_id": str(group_id)},
            )
        except Exception:
            logger.exception("Failed to log group-delete unshare for share=%s", share_id)
    return updated


def on_user_left_or_removed_from_group(user_id, group_id, *, reason: str = "left_group") -> dict:
    """
    Call when a user leaves or is kicked from a group.
    - Deactivates shares they created for that group.
    - Recipient access is revoked implicitly (membership checks).
    """
    try:
        n = deactivate_shares_created_by_user_in_group(user_id, group_id, reason=reason)
        return {"deactivated_created_shares": n}
    except Exception:
        logger.exception(
            "on_user_left_or_removed_from_group failed user=%s group=%s",
            user_id,
            group_id,
        )
        return {"deactivated_created_shares": 0, "error": True}


def on_group_deleted(group_id) -> dict:
    try:
        n = deactivate_all_shares_for_group(group_id, reason="group_deleted")
        return {"deactivated_shares": n}
    except Exception:
        logger.exception("on_group_deleted failed group=%s", group_id)
        return {"deactivated_shares": 0, "error": True}
