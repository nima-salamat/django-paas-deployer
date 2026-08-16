"""Invalidate admin user-list cache when User / Rule changes (Django admin + APIs)."""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_save, sender="users.User")
@receiver(post_delete, sender="users.User")
def _user_changed(sender, instance, **kwargs):
    try:
        from core.app_cache import invalidate_all_users_admin
        invalidate_all_users_admin()
    except Exception:
        pass


@receiver(post_save, sender="users.Rule")
@receiver(post_delete, sender="users.Rule")
def _rule_changed(sender, instance, **kwargs):
    try:
        from core.app_cache import invalidate_all_users_admin
        invalidate_all_users_admin()
    except Exception:
        pass
