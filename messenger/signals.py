import logging
import os
import shutil

from django.conf import settings
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Conversation, MessageAttachment, Message, PinnedMessage

logger = logging.getLogger("messenger.signals")


def _delete_quietly(path):
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


@receiver(pre_delete, sender=MessageAttachment)
def attachment_pre_delete(sender, instance, **kwargs):
    try:
        if instance.file and getattr(instance.file, "path", None):
            _delete_quietly(instance.file.path)
    except Exception:
        logger.exception("attachment file delete failed")


@receiver(pre_delete, sender=Conversation)
def conversation_pre_delete(sender, instance, **kwargs):
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
def message_pre_delete_pin_cleanup(sender, instance, **kwargs):
    """When a Message row is hard-deleted, remove its PinnedMessage row too.

    This covers:
    - Cascade deletes from ConversationCleanupAPIView
    - Any future hard-delete paths
    - The ORM CASCADE on PinnedMessage.message already handles this, but
      having an explicit signal ensures the pin row is gone BEFORE the
      message row (avoids potential integrity issues) and makes the
      behaviour visible/auditable.

    For soft-deletes (is_deleted=True), the MessageDeleteAPIView handles
    pin cleanup directly before setting is_deleted.
    """
    try:
        PinnedMessage.objects.filter(message_id=instance.pk).delete()
    except Exception:
        logger.exception("pin cleanup for message %s failed", instance.pk)
