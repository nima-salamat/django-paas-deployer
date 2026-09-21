from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate)
def seed_system_settings(sender, **kwargs):
    """Populate system settings after migrations complete.

    This defers DB writes until migrations have finished to avoid
    race conditions during startup and to ensure the database schema
    is in place.
    """
    try:
        from core.initial_config import seed_system_settings as _seed, seed_dockerfile_templates_from_config as _seed_templates
        # Only seed for the primary app label to avoid duplicate runs for multi-db setups
        if sender.name != 'core':
            return
        _seed(update_existing=False)
        _seed_templates()
    except Exception:
        # Never crash startup if seeding fails; it's best-effort
        import logging
        logging.getLogger(__name__).exception("SystemSetting seed skipped during post_migrate")
