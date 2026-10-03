"""Account-deletion side effects owned by the authentication subsystem."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .session_auth import invalidate_all_sessions

User = get_user_model()


@receiver(pre_delete, sender=User)
def user_pre_delete_cleanup(sender, instance, **kwargs):
    """Revoke durable sessions and schedule Redis session-key invalidation."""
    invalidate_all_sessions(instance.pk)
