from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_swarm_shell_accepts_any_running_replica_and_selects_a_task():
    source = (ROOT / "services/shell.py").read_text(encoding="utf-8")
    section = source.split("def _resolve_container", 1)[1].split(
        "def ", 1
    )[0]

    assert "state.replicas_running != 1" not in section
    assert "int(state.replicas_running or 0) <= 0" in section
    assert 'docker_service.tasks(filters={"desired-state": "running"})' in section
