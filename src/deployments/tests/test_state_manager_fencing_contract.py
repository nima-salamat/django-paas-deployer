from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_owned_transition_checks_fence_and_transition_under_one_lock():
    source = (ROOT / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    method = source.split("def transition_deploy_if_owned", 1)[1].split(
        "def transition_deploy_terminal_if_owned", 1
    )[0]

    assert "select_for_update" in method
    assert "execution_task_id != task_id" in method
    assert "cancel_requested" in method
    assert "check_deploy_transition" in method
    assert "Deploy.objects.filter(pk=deploy_id).update" in method
    assert "DeploymentEventOutbox.objects.create" in method


def test_terminal_compatibility_helper_delegates_to_owned_transition():
    source = (ROOT / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    method = source.split("def transition_deploy_terminal_if_owned", 1)[1].split(
        "__all__", 1
    )[0]

    assert "transition_deploy_if_owned" in method
    assert "terminal=True" in method


def test_deployment_claim_establishes_service_owner_for_heartbeat_fence():
    source = (ROOT / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    method = source.split("def lock_and_get_deployment", 1)[1].split(
        "def heartbeat_deploy", 1
    )[0]

    assert 'service.task_id = str(task_id)' in method
    assert '"task_id"' in method
    assert 'service.save(update_fields=["status", "deploy_started", "task_id"])' in method


def test_django_lifecycle_transition_does_not_shadow_state_manager_with_local_import():
    source = (ROOT / "deployments/infrastructure/django_lifecycle.py").read_text(encoding="utf-8")
    transition = source.split("def transition(", 1)[1].split(
        "def journal_runtime_resource", 1
    )[0]

    assert "from deployments.core.state.manager import StateManager" not in transition
    assert "from deployments.core.state.manager import StateManager" in source.split(
        "class DjangoDeploymentLifecycleStore", 1
    )[0]


def test_django_lifecycle_store_does_not_continue_after_cancel_wins_start_race():
    source = (ROOT / "deployments/infrastructure/django_lifecycle.py").read_text(
        encoding="utf-8"
    )

    assert "transitioned and self.status == sm.DEPLOY_RUNNING" in source
    assert "continue planning after that terminal decision" in source



def test_public_transition_has_no_terminal_outbox_authority():
    source = (ROOT / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    public_method = source.split("def transition_deploy(", 1)[1].split(
        "def activate_revision_and_succeed", 1
    )[0]
    assert "DeploymentEventOutbox.objects.create" not in public_method



def test_service_state_projection_invalidates_user_cache_after_commit():
    source = (ROOT / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    method = source.split("def transition_service(", 1)[1].split(
        "def transition_deploy(", 1
    )[0]

    assert "transaction.on_commit" in method
    assert "_invalidate_service_cache" in method
    assert "user_id = service.user_id" in method


def test_deployment_cancellation_preserves_reason_without_second_error_event():
    source = (ROOT / "deploy/deployment_state.py").read_text(encoding="utf-8")

    assert 'current.get("status_message")' in source
    assert 'current.get("error_message")' in source
    assert 'not isinstance(exception, DeploymentCancelled)' in source


def test_deploy_runtime_routing_fails_closed_instead_of_running_app_path():
    source = (ROOT / "deployments/celery/tasks.py").read_text(encoding="utf-8")
    guard = source.split("    # Guard: never run the app/zip pipeline for DB platforms", 1)[1].split(
        "    try:\n        # A cancelled deployment", 1
    )[0]
    assert "refusing app-path fallback" in guard
    assert "raise translated from exc" in guard
    assert "continuing app path" not in guard



def test_db_success_uses_same_activation_fence_as_native_lifecycle():
    source = (ROOT / "deployments/celery/tasks.py").read_text(encoding="utf-8")
    method = source.split("def _mark_success", 1)[1].split(
        "def _mark_failure", 1
    )[0]
    assert "expected_lifecycle_generation" in method
    assert "expected_previous_deploy_id" in method
    assert "enforce_previous_deploy=True" in method
    assert "getattr(service, " + ""lifecycle_generation"" + ", 0)" in method



def test_db_cancellation_uses_cancelled_deploy_state():
    source = (ROOT / "deployments/celery/tasks.py").read_text(encoding="utf-8")
    method = source.split("def _mark_failure", 1)[1].split(
        "def ", 1
    )[0]
    assert "target_status = (" in method
    assert "DeploymentStatusChoices.CANCELLED" in method
    assert 'str(stage or "").strip().lower() == "cancelled"' in method
    assert '"Database deployment cancelled."' in method

