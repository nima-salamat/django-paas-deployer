from django.apps import AppConfig


class ServicesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'services'

    def ready(self):
        try:
            from . import cache_signals  # noqa: F401
        except Exception:
            pass

        import services.signals