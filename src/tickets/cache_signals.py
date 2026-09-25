"""Invalidate ticket caches on Ticket / message changes (Django admin + APIs)."""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


def _bump_ticket(instance):
    try:
        from core.app_cache import invalidate_user_tickets
        uid = getattr(instance, "user_id", None)
        if uid:
            invalidate_user_tickets(uid)
    except Exception:
        pass


@receiver(post_save, sender="tickets.Ticket")
@receiver(post_delete, sender="tickets.Ticket")
def _ticket_changed(sender, instance, **kwargs):
    _bump_ticket(instance)


@receiver(post_save, sender="tickets.TicketMessage")
@receiver(post_delete, sender="tickets.TicketMessage")
def _ticket_message_changed(sender, instance, **kwargs):
    try:
        ticket = getattr(instance, "ticket", None)
        if ticket is not None:
            _bump_ticket(ticket)
    except Exception:
        pass
