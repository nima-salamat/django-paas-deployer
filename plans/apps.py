from django.apps import AppConfig


class PlansConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'plans'

    def ready(self):
        try:
            from . import cache_signals  # noqa: F401
        except Exception:
            pass
