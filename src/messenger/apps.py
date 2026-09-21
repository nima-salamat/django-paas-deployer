from django.apps import AppConfig


class MessengerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "messenger"
    verbose_name = "Messenger"

    def ready(self):
        try:
            from . import signals  # noqa: F401
        except ImportError:
            pass
