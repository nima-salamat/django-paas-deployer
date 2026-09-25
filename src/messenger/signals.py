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
                    _delete_quietly(att.file.path)
            except Exception:
                logger.exception("soft attachment file cleanup failed")
            try:
                att.delete()
            except Exception:
                logger.exception("soft attachment row cleanup failed")
    except Exception:
        logger.exception("soft attachment cleanup for message %s failed", message.pk)
