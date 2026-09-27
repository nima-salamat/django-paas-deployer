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


def test_service_revision_activation_keeps_legacy_projection_in_sync():
    source = (ROOT / "src" / "services" / "revisioning.py").read_text(encoding="utf-8")

    assert "selected_deploy_id = getattr(revision.source_deploy, \"pk\", None)" in source
    assert "selected_deploy=selected_deploy_id" in source
    assert "selected_deploy_at=timezone.now() if selected_deploy_id else None" in source


def test_start_service_bridges_legacy_selected_deploys():
    source = (ROOT / "src" / "services" / "api" / "runtime.py").read_text(encoding="utf-8")

    assert "ensure_active_revision_for_service" in source
    assert "This service has no deployable revision." in source


def test_successful_deployment_sync_uses_active_revision_as_authority():
    source = (ROOT / "src" / "deployments" / "celery" / "services" / "deploy_service.py").read_text(encoding="utf-8")

    assert "selected_id = None" not in source
    assert 'str(active_revision_id or "") == str(deploy_item.revision_id)' in source


def test_ticket_websocket_reads_user_flags_inside_sync_bridge():
    source = (ROOT / "src" / "tickets" / "consumers.py").read_text(encoding="utf-8")

    assert "is_staff, is_superuser = await self._user_flags(user)" in source
    assert "bool(user.is_staff), bool(user.is_superuser)" in source
