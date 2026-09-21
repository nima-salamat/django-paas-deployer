from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"

    def ready(self):
        try:
            import users.signals  # noqa: F401
        except Exception:
            pass
        try:
            from . import cache_signals  # noqa: F401
        except Exception:
            pass
