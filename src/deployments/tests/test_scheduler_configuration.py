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


def test_ready_app_deletion_can_cancel_rollback_children():
    state = (ROOT / "src" / "deployments" / "common" / "state_machine.py").read_text(encoding="utf-8")
    assert "(DEPLOY_ROLLING_BACK, DEPLOY_CANCELLED)" in state


def test_ready_app_pending_deletion_cannot_be_requeued_for_start():
    tasks = (ROOT / "src" / "app_catalog" / "tasks.py").read_text(encoding="utf-8")
    executor = (ROOT / "src" / "app_catalog" / "executor.py").read_text(encoding="utf-8")
    assert 'stage="deletion_pending"' in tasks
    assert 'instance.cancel_requested or instance.stage == "deletion_pending"' in executor


def test_ready_app_runtime_supervisor_is_scheduled_on_operations_queue():
    settings = (ROOT / "src" / "config" / "settings.py").read_text(encoding="utf-8")
    tasks = (ROOT / "src" / "app_catalog" / "tasks.py").read_text(encoding="utf-8")

    canonical = "app_catalog.supervise_ready_applications"

    assert f'"task": "{canonical}"' in settings
    assert f'"{canonical}": {{"queue": "operations"}}' in settings
    assert f'name="{canonical}"' in tasks


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

    assert 'if locked.status == "running":' in source
    assert "deployment_phase_remaining_seconds" in source
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


def test_deploy_terminal_sink_is_projection_only_and_preserves_uuid_ids():
    source = (ROOT / "src" / "deployments" / "core" / "sink.py").read_text(encoding="utf-8")

    assert "StateManager.transition_deploy(" not in source
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
    assert "StateManager.transition_deploy_system_terminal(" in source
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



def test_mariadb_readiness_uses_image_compatible_admin_client_with_fallback():
    source = (ROOT / "src" / "deployments" / "core" / "db_deployer.py").read_text(encoding="utf-8")

    helper = source.split("def _mysql_admin_ping(", 1)[1].split(
        "def _mysql_wait_until_ready(", 1
    )[0]
    assert '"mariadb-admin", "mysqladmin"' in helper
    assert '"mysqladmin", "mariadb-admin"' in helper
    assert "executable file not found" in helper
    assert "_mysql_admin_ping(" in source



def test_ready_app_deletion_task_is_routed_and_reconciled():
    settings = (ROOT / "src" / "config" / "settings.py").read_text(encoding="utf-8")
    tasks = (ROOT / "src" / "app_catalog" / "tasks.py").read_text(encoding="utf-8")
    assert '"app_catalog.delete_application_installation": {"queue": "operations"}' in settings
    deletion_query = tasks.split("instances = ApplicationInstance.objects.filter(", 1)[1].split(
        "    recovered = 0", 1
    )[0]
    assert "ApplicationStatus.RUNNING" in deletion_query
    assert 'stage="deletion_pending"' in deletion_query
    assert 'name="app_catalog.delete_application_installation"' in tasks
    assert 'max_retries=None' in tasks
    assert 'stage="deletion_pending"' in tasks
    assert 'delete_application_installation.delay(str(pending.pk))' in tasks


def test_ready_app_deletion_reconciliation_does_not_require_stale_updated_at():
    tasks = (ROOT / "src" / "app_catalog" / "tasks.py").read_text(encoding="utf-8")
    deletion_section = tasks.split(
        "def reconcile_application_installations():", 1
    )[1].split(
        "    # Recover application coordinators whose creation transaction committed",
        1,
    )[0]
    assert 'stage="deletion_pending"' in deletion_section
    assert "cleanup_terminal_application()" in deletion_section
    assert "updated_at__lt=cutoff" not in deletion_section


def test_service_state_manager_invalidates_cache_after_direct_service_updates():
    source = (ROOT / "src" / "deployments" / "core" / "state" / "manager.py").read_text(encoding="utf-8")

    transition = source.split("def transition_service(", 1)[1].split(
        "def transition_deploy(", 1
    )[0]
    activation = source.split("def activate_revision_and_succeed(", 1)[1].split(
        "def transition_deploy_system_terminal(", 1
    )[0]

    assert "transaction.on_commit" in transition
    assert "_invalidate_service_cache" in transition
    assert "transaction.on_commit" in activation


def test_dependency_cancelled_deployments_are_not_labeled_as_user_cancelled_errors():
    executor = (ROOT / "src" / "app_catalog" / "executor.py").read_text(encoding="utf-8")
    state = (ROOT / "src" / "deploy" / "deployment_state.py").read_text(encoding="utf-8")

    failure_section = executor.split("if failed:", 1)[1].split("required_bindings", 1)[0]
    assert "required application service" in failure_section
    assert '"error_message": ""' in failure_section
    assert "Deployment cancelled by the user." in state
    assert 'current.get("status_message")' in state
    assert 'not isinstance(exception, DeploymentCancelled)' in state
