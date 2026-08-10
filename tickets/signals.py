from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Ticket, TicketMessage


@receiver(post_save, sender=Ticket)
def ticket_saved(sender, instance, created, **kwargs):
    try:
        from .consumers import broadcast_ticket_event
        # ensure department/user available
        if instance.department_id and not hasattr(instance, "_prefetched_objects_cache"):
            try:
                _ = instance.department
                _ = instance.user
            except Exception:
                pass
        event = "ticket.created" if created else "ticket.updated"
        broadcast_ticket_event(event, instance)
    except Exception:
        pass


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
            },
        )
    except Exception:
        pass
