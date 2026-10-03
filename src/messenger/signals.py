import logging
import os
import shutil

from django.conf import settings
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import Conversation, ConversationParticipant, MessageAttachment, Message, PinnedMessage

logger = logging.getLogger("messenger.signals")
User = get_user_model()


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
