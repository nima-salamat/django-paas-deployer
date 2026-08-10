from django.apps import AppConfig


class TicketsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tickets"
    verbose_name = "Ticketing System"

    def ready(self):
        try:
            from . import signals  # noqa: F401
        except ImportError:
            pass
