from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_monitor_can_recover_failed_projection_only_with_current_runtime_intent():
    actions = (
        ROOT / "src" / "deployments" / "celery" / "monitoring" / "actions.py"
    ).read_text(encoding="utf-8")
    schedules = (
        ROOT / "src" / "deployments" / "celery" / "schedules.py"
    ).read_text(encoding="utf-8")

    running = actions.split("def mark_service_running(", 1)[1].split(
        "def mark_service_stopped(", 1
    )[0]
    reconciliation = schedules.split(
        "def _reconcile_service_runtime_swarm(", 1
    )[1].split("def _reconcile_base_runtime_builds(", 1)[0]

    assert "SERVICE_STATUS_CHOICES.FAILED" in running
    assert "allow_runtime_reconciliation=allow_runtime_reconciliation" in running
    assert "expected_lifecycle_generation=expected_lifecycle_generation" in running
    assert "expected_desired_state=expected_desired_state" in running
    assert "allow_runtime_reconciliation=True" in reconciliation
    assert 'expected_desired_state="running"' in reconciliation
    assert "cleanup_stopped_task_containers()" in reconciliation


def test_monitor_does_not_repair_failed_service_without_a_converged_runtime():
    schedules = (
        ROOT / "src" / "deployments" / "celery" / "schedules.py"
    ).read_text(encoding="utf-8")
    reconciliation = schedules.split(
        "def _reconcile_service_runtime_swarm(", 1
    )[1].split("def _reconcile_base_runtime_builds(", 1)[0]

    assert (
        "decision.action is ReconciliationAction.CONVERGED"
        in reconciliation
    )
    assert "if decision.action is ReconciliationAction.CONVERGED:" in reconciliation
    assert "decision.action is ReconciliationAction.STOP and result.success" in reconciliation
    assert "elif result.success and decision.action in {" in reconciliation
