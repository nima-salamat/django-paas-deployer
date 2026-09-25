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


def test_terminal_compatibility_helper_delegates_to_owned_transition():
    source = (ROOT / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    method = source.split("def transition_deploy_terminal_if_owned", 1)[1].split(
        "__all__", 1
    )[0]

    assert "transition_deploy_if_owned" in method
    assert "terminal=True" in method
