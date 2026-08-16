from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender="tickets.Ticket")
@receiver(post_delete, sender="tickets.Ticket")
def _ticket_changed(sender, instance, **kwargs):
    try:
        from core.app_cache import invalidate_user_tickets
        uid = getattr(instance, "user_id", None)
        if uid:
            invalidate_user_tickets(uid)
    except Exception:
        pass
