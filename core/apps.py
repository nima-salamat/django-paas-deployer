# core/apps.py — full file
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Defer heavy DB seeding until after migrations via post_migrate signal
        # Import the signals module to ensure receivers are registered.
        try:
            import core.signals  # noqa: F401
        except Exception:
            # Never block startup if signals can't be imported
            pass
