"""Invalidate service caches on ANY ORM change (Django admin + APIs + shell).

Django admin uses Model.save()/delete() → post_save / post_delete fire
the same way as API writes. No extra admin hooks required.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


def _bump_service(instance):
    try:
        from core.app_cache import invalidate_user_services, invalidate_all_services
        uid = getattr(instance, "user_id", None)
        if uid:
            invalidate_user_services(uid)
        else:
            invalidate_all_services()
    except Exception:
        pass


@receiver(post_save, sender="services.Service")
@receiver(post_delete, sender="services.Service")
def _service_changed(sender, instance, **kwargs):
    _bump_service(instance)


@receiver(post_save, sender="services.PrivateNetwork")
@receiver(post_delete, sender="services.PrivateNetwork")
def _network_changed(sender, instance, **kwargs):
    _bump_service(instance)


@receiver(post_save, sender="services.Volume")
@receiver(post_delete, sender="services.Volume")
def _volume_changed(sender, instance, **kwargs):
    try:
        svc = getattr(instance, "service", None)
        if svc is not None:
            _bump_service(svc)
        else:
            from core.app_cache import invalidate_all_services
            invalidate_all_services()
    except Exception:
        pass
