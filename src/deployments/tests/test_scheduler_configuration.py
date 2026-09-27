"""Regression tests for deployment scheduler wiring."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_swarm_sync_uses_django_timezone_api():
    source = (ROOT / "src" / "deployments" / "core" / "swarm.py").read_text(encoding="utf-8")

    assert "from django.utils import timezone" in source
    assert "now = timezone.now()" in source
    assert '__import__("django.utils.timezone", fromlist=["timezone"]).timezone.now()' not in source


def test_application_catalog_reconcile_schedule_matches_registered_task_name():
    settings = (ROOT / "src" / "config" / "settings.py").read_text(encoding="utf-8")
    tasks = (ROOT / "src" / "app_catalog" / "tasks.py").read_text(encoding="utf-8")

    canonical = "app_catalog.reconcile_application_installations"
    legacy_wrong = "app_catalog.tasks.reconcile_application_installations"

    assert f'"task": "{canonical}"' in settings
    assert canonical in tasks
    assert f'"task": "{legacy_wrong}"' not in settings


def test_deployment_log_tasks_are_explicitly_registered():
    celery = (ROOT / "src" / "config" / "celery.py").read_text(encoding="utf-8")

    assert "'logs.tasks'" in celery
    assert "'logs'," in celery
