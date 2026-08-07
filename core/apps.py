# core/apps.py — full file
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Seed system settings after migrations (ignore errors during migrate)
        try:
            from django.db.utils import OperationalError, ProgrammingError
            from core.initial_config import (
                seed_system_settings,
                seed_dockerfile_templates_from_config,
            )

            seed_system_settings(update_existing=False)
            seed_dockerfile_templates_from_config()
        except (OperationalError, ProgrammingError):
            pass
        except Exception:
            # Never block startup
            import logging

            logging.getLogger(__name__).exception("SystemSetting seed skipped")
