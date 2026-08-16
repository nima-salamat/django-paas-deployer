from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender="plans.Plan")
@receiver(post_delete, sender="plans.Plan")
def _plan_changed(sender, instance, **kwargs):
    try:
        from core.app_cache import invalidate_all_plans
        invalidate_all_plans()
    except Exception:
        pass
