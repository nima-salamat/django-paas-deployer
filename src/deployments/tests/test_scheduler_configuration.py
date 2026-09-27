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


def test_locked_revision_queries_do_not_join_nullable_source_deploy():
    revisioning = (ROOT / "src" / "services" / "revisioning.py").read_text(encoding="utf-8")
    authority = (ROOT / "src" / "services" / "lifecycle" / "authority.py").read_text(encoding="utf-8")

    expected = '''    qs = ServiceRevision.objects.all()
    if for_update:
        # Do not select_related() nullable source_deploy while applying
        # PostgreSQL FOR UPDATE; that produces a forbidden outer join.
        qs = qs.select_for_update()
    else:
        qs = qs.select_related("source_deploy")
'''

    assert expected in revisioning
    assert expected in authority


def test_locked_deploy_revision_compilation_does_not_join_nullable_relations():
    source = (ROOT / "src" / "services" / "revisioning.py").read_text(encoding="utf-8")

    locked_section = source.split("def ensure_revision_for_deploy", 1)[1].split("def ", 1)[0]
    assert "Deploy.objects.select_for_update().get(pk=deploy.pk)" in locked_section
    assert '.select_related("service", "created_by")' not in locked_section


def test_rebuild_handles_stopped_service_and_reexecutes_succeeded_deploy():
    apis = (ROOT / "src" / "deploy" / "apis.py").read_text(encoding="utf-8")
    state_machine = (ROOT / "src" / "deployments" / "common" / "state_machine.py").read_text(encoding="utf-8")

    assert 'if service.status != SERVICE_STATUS_CHOICES.STOPPED:' in apis
    assert "(DEPLOY_SUCCEEDED, DEPLOY_PENDING)" in state_machine


def test_revision_artifact_initial_write_bypasses_immutable_model_save():
    source = (ROOT / "src" / "services" / "revisioning.py").read_text(encoding="utf-8")

    assert "ServiceRevision.objects.filter(pk=revision.pk).update(" in source
    assert 'artifact_file=revision.artifact_file.name' in source
    assert 'revision.save(update_fields=["artifact_file", "updated_at"])' not in source


def test_pending_deploys_are_not_timed_out_from_stale_started_at():
    source = (ROOT / "src" / "deployments" / "celery" / "schedules.py").read_text(encoding="utf-8")

    assert 'if locked.status == "running" and locked.started_at:' in source
    assert 'status=DeploymentStatusChoices.PENDING,' in source
    assert 'cancel_requested=False,' in source
    assert 'updated_at__lt=cutoff' in source


def test_service_state_facade_forwards_deployment_task_owner():
    source = (ROOT / "src" / "deployments" / "celery" / "service_status.py").read_text(encoding="utf-8")

    assert "task_id: str | None = None" in source
    assert "StateManager.lock_and_get_deployment(" in source
    assert "task_id=task_id" in source


def test_monitor_can_terminalize_a_failed_queued_service():
    source = (ROOT / "src" / "deployments" / "common" / "state_machine.py").read_text(encoding="utf-8")

    assert "(SERVICE_QUEUED, SERVICE_FAILED)" in source


def test_deploy_terminal_sink_preserves_uuid_deployment_ids():
    source = (ROOT / "src" / "deployments" / "core" / "sink.py").read_text(encoding="utf-8")

    assert "self.deployment_id, terminal_transition[0]," in source
    assert "int(self.deployment_id)" not in source


def test_pending_transition_resets_previous_execution_timestamps():
    source = (ROOT / "src" / "deployments" / "core" / "state" / "manager.py").read_text(encoding="utf-8")

    assert 'if target == sm.DEPLOY_PENDING:' in source
    assert 'updates.setdefault("started_at", None)' in source
    assert 'updates.setdefault("completed_at", None)' in source


def test_pending_cancelled_deployments_have_a_terminal_recovery_path():
    schedules = (ROOT / "src" / "deployments" / "celery" / "schedules.py").read_text(encoding="utf-8")
    state_machine = (ROOT / "src" / "deployments" / "common" / "state_machine.py").read_text(encoding="utf-8")

    assert "def _finalize_pending_cancellations() -> None:" in schedules
    assert "status=DeploymentStatusChoices.PENDING," in schedules
    assert "cancel_requested=True," in schedules
    assert 'DeploymentStatusChoices.CANCELLED' in schedules
    assert "(SERVICE_QUEUED, SERVICE_STOPPED)" in state_machine


def test_force_cancel_runtime_imports_deployment_state_and_uses_state_manager():
    source = (ROOT / "src" / "services" / "api" / "runtime.py").read_text(encoding="utf-8")

    assert "from deploy.models import Deploy, DeploymentStatusChoices" in source
    assert "StateManager.transition_deploy(" in source
    assert "DeploymentStatusChoices.CANCELLED" in source
    assert 'active_states = {"pending", "queued", "running", "deploying", "stopping"}' not in source


def test_compose_workers_isolate_base_image_queue_from_deployment_workers():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "base-image-worker:" in compose
    base_worker = compose.split("base-image-worker:", 1)[1]
    deployment_worker = compose.split("deployment-worker:", 1)[1].split("base-image-worker:", 1)[0]
    assert "-Q" in base_worker
    assert "base-images" in base_worker
    assert "base-images" not in deployment_worker
