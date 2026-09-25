import logging
import os
import re
import shutil

from django.conf import settings
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from .models import Ticket, TicketAttachment, TicketMessage

logger = logging.getLogger("tickets.signals")


def _preview(html: str, n=80) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n]


@receiver(post_save, sender=Ticket)
def ticket_saved(sender, instance, created, **kwargs):
    try:
        from .consumers import broadcast_ticket_event
        event = "ticket.created" if created else "ticket.updated"
        broadcast_ticket_event(event, instance)
    except Exception:
        logger.exception("ticket_saved broadcast failed")


@receiver(post_save, sender=TicketMessage)
def ticket_message_saved(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from .consumers import broadcast_ticket_event
        ticket = instance.ticket
        author = instance.author
        broadcast_ticket_event(
            "ticket.message",
            ticket,
            extra={
                "message_id": instance.id,
                "is_staff_reply": instance.is_staff_reply,
                "author_id": instance.author_id,
                "preview": _preview(instance.body),
                "username": getattr(author, "username", None) if author else None,
            },
        )
    except Exception:
        logger.exception("ticket_message_saved broadcast failed")


def _delete_file_quietly(path: str) -> None:
    """Remove a single media file if it exists; never raise."""
    if not path:
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
            logger.debug("Deleted attachment file: %s", path)
    except OSError as exc:
        logger.warning("Could not delete file %s: %s", path, exc)


def _ticket_media_dir(ticket_id) -> str:
    """Absolute path of tickets/<ticket_id>/ under MEDIA_ROOT."""
    media_root = getattr(settings, "MEDIA_ROOT", None)
    if not media_root:
        return ""
    return os.path.join(str(media_root), "tickets", str(ticket_id))


@receiver(pre_delete, sender=TicketAttachment)
def ticket_attachment_pre_delete(sender, instance, **kwargs):
    """Delete the physical file when an attachment row is removed."""
    try:
        if instance.file and getattr(instance.file, "path", None):
            _delete_file_quietly(instance.file.path)
    except Exception:
        logger.exception(
            "ticket_attachment_pre_delete failed for attachment %s",
            getattr(instance, "pk", None),
        )


@receiver(pre_delete, sender=Ticket)
def ticket_pre_delete(sender, instance, **kwargs):
    """
    Before a ticket is deleted:
    - Delete every attachment file on disk
    - Remove the tickets/<ticket_id>/ directory entirely
    """
    ticket_id = instance.pk
    try:
        attachments = TicketAttachment.objects.filter(ticket_id=ticket_id)
        for att in attachments:
            try:
                if att.file and getattr(att.file, "path", None):
                    _delete_file_quietly(att.file.path)
            except Exception:
                logger.exception("Failed deleting file for attachment %s", att.pk)

        dir_path = _ticket_media_dir(ticket_id)
        if dir_path and os.path.isdir(dir_path):
            try:
                shutil.rmtree(dir_path, ignore_errors=False)
                logger.info("Removed ticket media directory: %s", dir_path)
            except OSError as exc:
                logger.warning("Could not rmtree %s: %s", dir_path, exc)
                try:
                    for root, dirs, files in os.walk(dir_path, topdown=False):
                        for name in files:
                            _delete_file_quietly(os.path.join(root, name))
                        for name in dirs:
                            try:
                                os.rmdir(os.path.join(root, name))
                            except OSError:
                                pass
                    if os.path.isdir(dir_path):
                        os.rmdir(dir_path)
                except Exception:
                    logger.exception("Fallback cleanup of %s failed", dir_path)
    except Exception:
        logger.exception("ticket_pre_delete cleanup failed for ticket %s", ticket_id)


@receiver(post_delete, sender=Ticket)
def ticket_post_delete(sender, instance, **kwargs):
    """Safety net: ensure the media folder is gone after cascade."""
    try:
        dir_path = _ticket_media_dir(instance.pk)
        if dir_path and os.path.isdir(dir_path):
            shutil.rmtree(dir_path, ignore_errors=True)
            logger.info("post_delete cleaned ticket media dir: %s", dir_path)
    except Exception:
        logger.exception(
            "ticket_post_delete cleanup failed for ticket %s",
            getattr(instance, "pk", None),
        )
