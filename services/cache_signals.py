"""Invalidate service caches on model changes (Django admin + ORM)."""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender="services.Service")
@receiver(post_delete, sender="services.Service")
def _svc_changed(sender, instance, **kwargs):
    try:
        from core.app_cache import invalidate_user_services, invalidate_all_services
        uid = getattr(instance, "user_id", None)
        if uid:
            invalidate_user_services(uid)
        else:
            invalidate_all_services()
    except Exception:
        pass
