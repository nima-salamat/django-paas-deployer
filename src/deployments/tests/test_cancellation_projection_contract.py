from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_all_terminal_cancel_paths_restore_service_projection():
    source = (ROOT / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    owned = source.split("def transition_deploy_if_owned", 1)[1].split(
        "def mark_deploy_retry_pending", 1
    )[0]
    system = source.split("def transition_deploy_system_terminal", 1)[1].split(
        "def finalize_pending_cancellation", 1
    )[0]
    retry = source.split("def mark_deploy_retry_pending", 1)[1].split(
        "def transition_deploy_terminal_if_owned", 1
    )[0]
    pending = source.split("def finalize_pending_cancellation", 1)[1].split(
        "def lock_and_get_deployment", 1
    )[0]

    assert "_project_service_after_cancellation(" in owned
    assert "_project_service_after_cancellation(" in system
    assert "return cls.transition_deploy_if_owned(" in retry
    assert "_project_service_after_cancellation(" in pending


def test_cancel_projection_preserves_previous_release_and_desired_intent():
    source = (ROOT / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    helper = source.split("def _project_service_after_cancellation", 1)[1].split(
        "def transition_deploy(", 1
    )[0]

    assert 'desired_state == "deleted"' in helper
    assert 'desired_state == "stopped"' in helper
    assert "active_revision_id" in helper
    assert "selected_deploy_id" in helper
    assert "cleanup_failed" in helper
    assert "SERVICE_STATUS_CHOICES.RUNNING" in helper
    assert "SERVICE_STATUS_CHOICES.STOPPED" in helper
    assert "SERVICE_STATUS_CHOICES.FAILED" in helper


def test_retry_cancellation_uses_the_same_durable_terminal_path():
    source = (ROOT / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    retry = source.split("def mark_deploy_retry_pending", 1)[1].split(
        "def transition_deploy_terminal_if_owned", 1
    )[0]

    assert "cancellation_won_retry_race" in retry
    assert "terminal=True" in retry
    assert "event_payload=payload" in retry
    assert "Deploy.objects.filter(pk=deploy_id).update(**updates)" not in retry.split(
        "cancellation_message =", 1
    )[1]
