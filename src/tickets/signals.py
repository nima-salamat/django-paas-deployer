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


def _ticket_media_dir(ticket_id) -> str:
    """Absolute path of tickets/<ticket_id>/ under MEDIA_ROOT."""
    media_root = getattr(settings, "MEDIA_ROOT", None)
    if not media_root:
        return ""
    return os.path.join(str(media_root), "tickets", str(ticket_id))


@receiver(pre_delete, sender=TicketAttachment)
def ticket_attachment_pre_delete(sender, instance, **kwargs):
    """Delete the stored file before its attachment row disappears."""
    if not instance.file:
        return
    name = str(getattr(instance.file, "name", "") or "")
    try:
        instance.file.delete(save=False)
    except Exception as exc:
        logger.exception(
            "ticket_attachment_pre_delete failed for attachment %s",
            getattr(instance, "pk", None),
        )
        raise RuntimeError(
            f"Failed to remove ticket attachment '{name}'."
        ) from exc


@receiver(pre_delete, sender=Ticket)
def ticket_pre_delete(sender, instance, **kwargs):
    """Leave attachment storage cleanup to TicketAttachment.pre_delete.

    Keeping directory cleanup in post_delete avoids touching the filesystem
    before the collector has successfully removed every attachment row.
    """
    return
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
