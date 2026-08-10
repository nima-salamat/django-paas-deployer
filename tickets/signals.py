import logging
import re

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Ticket, TicketMessage

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
        broadcast_ticket_event(
            "ticket.message",
            ticket,
            extra={
                "message_id": instance.id,
                "is_staff_reply": instance.is_staff_reply,
                "author_id": instance.author_id,
                "preview": _preview(instance.body),
            },
        )
    except Exception:
        logger.exception("ticket_message_saved broadcast failed")
