import logging
import os
import shutil

from django.conf import settings
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.auth import get_user_model

from .models import Conversation, ConversationParticipant, MessageAttachment, Message, PinnedMessage

logger = logging.getLogger("messenger.signals")
User = get_user_model()


@receiver(pre_save, sender=ConversationParticipant)
def remember_previous_forum_membership_state(sender, instance, **kwargs):
    """Record only the root-forum membership transition needed by topic sync."""
    instance._messenger_previous_root_left_at = None
    if not instance.pk:
        return

    previous = (
        ConversationParticipant.objects
        .filter(pk=instance.pk)
        .values(
            "left_at",
            "conversation__parent_conversation_id",
            "conversation__is_forum",
        )
        .first()
    )
    if (
        previous
        and previous["conversation__parent_conversation_id"] is None
        and previous["conversation__is_forum"]
    ):
        instance._messenger_previous_root_left_at = previous["left_at"]


@receiver(post_save, sender=ConversationParticipant)
def sync_forum_topic_membership(sender, instance, created=False, **kwargs):
    """
    Synchronize active root membership and permissions into forum topics.

    A topic-local removal must not be undone by an unrelated role/permission
    edit on the root group. A removed topic member is reactivated only when
    their root membership is newly created or explicitly transitions from
    left to active. Child conversation saves never recurse here.
    """
    conversation = instance.conversation
    if conversation.parent_conversation_id or not conversation.is_forum:
        return

    topic_ids = list(conversation.topic_conversations.values_list("id", flat=True))
    if not topic_ids:
        return

    policy = {
        "role": instance.role,
        "can_send_messages": instance.can_send_messages,
        "can_send_media": instance.can_send_media,
        "can_add_members": instance.can_add_members,
        "can_pin_messages": instance.can_pin_messages,
        "can_change_info": instance.can_change_info,
    }
    now = timezone.now()
    rejoined_root = instance.left_at is None and (
        created or getattr(instance, "_messenger_previous_root_left_at", None) is not None
    )
    for topic_id in topic_ids:
        topic_member = ConversationParticipant.objects.filter(
            conversation_id=topic_id, user_id=instance.user_id
        ).first()
        if topic_member is None:
            if instance.left_at is None:
                ConversationParticipant.objects.create(
                    conversation_id=topic_id,
                    user_id=instance.user_id,
                    **policy,
                )
            continue

        changed_fields = []
        if instance.left_at is None:
            if topic_member.left_at is not None:
                if not rejoined_root:
                    # Preserve a deliberate topic-level removal during ordinary
                    # root group role/permission changes.
                    continue
                topic_member.left_at = None
                topic_member.joined_at = now
                changed_fields.extend(("left_at", "joined_at"))

            for field, value in policy.items():
                if getattr(topic_member, field) != value:
                    setattr(topic_member, field, value)
                    changed_fields.append(field)
        elif topic_member.left_at is None:
            topic_member.left_at = instance.left_at or now
            changed_fields.append("left_at")

        if changed_fields:
            topic_member.save(update_fields=sorted(set(changed_fields)))


def _delete_quietly(file_field):
    """Delete a Django storage object without making cleanup fatal."""
    try:
        if file_field:
            file_field.delete(save=False)
    except Exception:
        logger.exception("media object cleanup failed")


@receiver(pre_delete, sender=User)
def user_pre_delete_cleanup(sender, instance, **kwargs):
    """Apply Messenger leave semantics before the account cascade."""
    user_id = int(instance.pk)
    memberships = list(
        ConversationParticipant.objects
        .select_related("conversation")
        .filter(user_id=user_id)
    )
    message_conversation_ids = list(
        Message.objects.filter(sender_id=user_id)
        .values_list("conversation_id", flat=True)
        .distinct()
    )
    conversation_ids = {
        int(value)
        for value in list(
            membership.conversation_id for membership in memberships
        ) + message_conversation_ids
        if value is not None
    }
    affected_users = {user_id}
    try:
        for uid in ConversationParticipant.objects.filter(
            conversation_id__in=conversation_ids,
        ).values_list("user_id", flat=True):
            affected_users.add(int(uid))
    except Exception:
        logger.exception(
            "Could not collect Messenger cache peers for deleted user=%s",
            user_id,
        )

    try:
        from .message_cache import MessageCacheService, ConversationCacheService
        for conv_id in sorted(conversation_ids):
            MessageCacheService.invalidate_chat_cache(conv_id)
            ConversationCacheService.invalidate_participants(conv_id)
        for uid in affected_users:
            ConversationCacheService.invalidate_user_conv_list(uid)
        from .consumers import _broadcast_presence
        if user_id:
            _broadcast_presence(user_id, False)
    except Exception:
        logger.exception("Messenger cache/presence cleanup failed for deleted user=%s", user_id)

    for membership in memberships:
        conversation = membership.conversation
        others = list(
            ConversationParticipant.objects
            .filter(conversation_id=conversation.pk, left_at__isnull=True)
            .exclude(user_id=user_id)
            .values_list("user_id", flat=True)
        )
        affected_users.update(int(uid) for uid in others)

        if conversation.type == Conversation.Type.PRIVATE:
            conversation.delete()
            continue

        try:
            from services.share_cleanup import on_user_left_or_removed_from_group
            result = on_user_left_or_removed_from_group(user_id, conversation.pk, reason="user_deleted")
            if result.get("error"):
                raise RuntimeError(
                    f"Failed to clean service shares for deleted user={user_id} group={conversation.pk}"
                )
        except Exception:
            logger.exception(
                "Service-share cleanup failed for deleted user=%s group=%s",
                user_id, conversation.pk,
            )
            raise

        if membership.role == ConversationParticipant.Role.OWNER:
            from .api.members import _auto_transfer_or_cleanup
            _auto_transfer_or_cleanup(conversation, membership)


@receiver(post_delete, sender=User)
def user_post_delete_cleanup(sender, instance, **kwargs):
    """Invalidate user-scoped Messenger caches and presence after deletion."""
    user_id = int(instance.pk)
    try:
        from .message_cache import ConversationCacheService
        ConversationCacheService.invalidate_user_conv_list(user_id)
    except Exception:
        logger.exception("Messenger list cache cleanup failed for deleted user=%s", user_id)
    try:
        from django.core.cache import cache
        cache.delete(f"messenger:online:{user_id}")
        cache.delete(f"messenger:online_conns:{user_id}")
    except Exception:
        logger.exception("Messenger presence cache cleanup failed for deleted user=%s", user_id)

@receiver(pre_delete, sender=MessageAttachment)
def attachment_pre_delete(sender, instance, **kwargs):
    try:
        if instance.file:
            instance.file.delete(save=False)
    except Exception as exc:
        logger.exception("attachment file delete failed")
        raise RuntimeError(
            f"Failed to remove messenger attachment '{getattr(instance.file, 'name', '')}'."
        ) from exc


@receiver(pre_delete, sender=Conversation)
def conversation_pre_delete(sender, instance, **kwargs):
    # Deleting a group must revoke all service shares targeting it before the
    # Conversation row disappears. Share rows later CASCADE, but this preserves
    # the authorization/audit side-effect contract.
    if instance.type == Conversation.Type.GROUP:
        try:
            from services.share_cleanup import on_group_deleted
            result = on_group_deleted(instance.pk)
            if result.get("error"):
                raise RuntimeError(
                    f"Failed to clean service shares for deleted group={instance.pk}"
                )
        except Exception:
            logger.exception(
                "service share cleanup failed before conversation delete group=%s",
                instance.pk,
            )
            raise

    try:
        if instance.avatar:
            instance.avatar.delete(save=False)
    except Exception:
        logger.exception(
            "conversation avatar cleanup failed conv=%s",
            instance.pk,
        )
        raise

    media_root = getattr(settings, "MEDIA_ROOT", None)
    if not media_root:
        return
    dir_path = os.path.join(str(media_root), "messenger", str(instance.pk))
    if os.path.isdir(dir_path):
        try:
            shutil.rmtree(dir_path, ignore_errors=True)
        except Exception:
            logger.exception("conv media cleanup failed")


@receiver(pre_delete, sender=Message)
def message_pre_delete_cleanup(sender, instance, **kwargs):
    """Hard-delete side effects for Message rows.

    - Remove PinnedMessage rows explicitly (CASCADE would also do this;
      signal keeps behaviour auditable and runs before the row is gone).
    - Attachment files are cleaned by MessageAttachment.pre_delete via CASCADE.
    """
    try:
        PinnedMessage.objects.filter(message_id=instance.pk).delete()
    except Exception:
        logger.exception("pin cleanup for message %s failed", instance.pk)


def soft_delete_message_side_effects(message):
    """Shared cleanup for soft-deletes (API delete + cancel-schedule).

    Removes pins and attachment files so cancelled scheduled messages never
    leave orphan media, and soft-deleted messages drop pins consistently.
    """
    if not message or not getattr(message, "pk", None):
        return
    try:
        PinnedMessage.objects.filter(message_id=message.pk).delete()
    except Exception:
        logger.exception("soft pin cleanup for message %s failed", message.pk)

    try:
        for att in MessageAttachment.objects.filter(message_id=message.pk):
            try:
                if att.file and getattr(att.file, "path", None):
                    _delete_quietly(att.file)
            except Exception:
                logger.exception("soft attachment file cleanup failed")
            try:
                att.delete()
            except Exception:
                logger.exception("soft attachment row cleanup failed")
    except Exception:
        logger.exception("soft attachment cleanup for message %s failed", message.pk)
