"""Low-footprint Celery Beat producer application.

Beat only publishes task names from the configured schedules; it does not
execute tasks. Keep the database-backed scheduler for operator-managed
PeriodicTask rows while avoiding imports of deployment/Docker task modules.
"""
from __future__ import annotations

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

# The database scheduler needs django-celery-beat's models, but the Beat
# process does not need to import every application's task implementation.
django.setup()

from celery import Celery

app = Celery("config", fixups=[])
app.config_from_object("django.conf:settings", namespace="CELERY", force=True)

# Prevent CELERY_IMPORTS / include from loading worker implementation modules.
# send_task() publishes the string task names without requiring local registry
# entries. Actual execution remains in normal worker processes.
app.conf.update(
    imports=(),
    include=(),
    # Keep the namespaced Django setting from taking precedence through the
    # Celery settings alias map after the lowercase override is applied.
    CELERY_IMPORTS=(),
)
