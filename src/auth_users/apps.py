from django.apps import AppConfig


class AuthUsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'auth_users'

    def ready(self):
        from . import deletion_signals  # noqa: F401
