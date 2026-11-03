"""Regression tests for lifecycle-fenced force rebuild teardown."""

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.lifecycle import rebuild


ROOT = Path(__file__).resolve().parents[2]


def _service():
    return SimpleNamespace(
        pk="service-123",
        get_docker_service_name=lambda: "app-service-123",
    )


def test_force_rebuild_takes_transaction_lock_and_fences_before_swarm_removal(monkeypatch):
    events = []

    @contextmanager
    def lock(service_id):
        events.append(("lock", service_id))
        yield
        events.append(("unlock", service_id))

    class Runtime:
        def remove_service_group(self, service_id):
            events.append(("remove", service_id))

    monkeypatch.setattr(rebuild, "acquire_service_deployment_transaction_lock", lock)
    monkeypatch.setattr(
        rebuild,
        "bump_lifecycle",
        lambda service_id, desired_state: (
            events.append(("fence", service_id, desired_state)) or 17
        ),
    )
    monkeypatch.setattr(rebuild, "swarm_enabled", lambda: True)
    monkeypatch.setattr(rebuild, "SwarmRuntime", Runtime)

    generation, error = rebuild.fence_and_teardown_service_runtime(
        _service(),
        platform="docker",
    )

    assert generation == 17
    assert error is None
    assert events == [
        ("lock", "service-123"),
        ("fence", "service-123", "running"),
        ("remove", "service-123"),
        ("unlock", "service-123"),
    ]


def test_force_rebuild_returns_teardown_error_after_fencing_instead_of_raising(monkeypatch):
    events = []

    @contextmanager
    def lock(service_id):
        events.append("lock")
        yield

    class Runtime:
        def remove_service_group(self, service_id):
            events.append("remove")
            raise RuntimeError("Swarm manager unavailable")

    monkeypatch.setattr(rebuild, "acquire_service_deployment_transaction_lock", lock)
    monkeypatch.setattr(
        rebuild,
        "bump_lifecycle",
        lambda service_id, desired_state: (
            events.append("fence") or 23
        ),
    )
    monkeypatch.setattr(rebuild, "swarm_enabled", lambda: True)
    monkeypatch.setattr(rebuild, "SwarmRuntime", Runtime)

    generation, error = rebuild.fence_and_teardown_service_runtime(
        _service(),
        platform="docker",
    )

    assert generation == 23
    assert error == "Swarm manager unavailable"
    assert events == ["lock", "fence", "remove"]


def test_force_rebuild_does_not_teardown_when_lifecycle_lock_is_unavailable(monkeypatch):
    def lock(_service_id):
        raise RuntimeError("service has an active lifecycle operation")

    def unexpected_fence(*_args, **_kwargs):
        raise AssertionError("generation must not be bumped without the lock")

    monkeypatch.setattr(rebuild, "acquire_service_deployment_transaction_lock", lock)
    monkeypatch.setattr(rebuild, "bump_lifecycle", unexpected_fence)

    with pytest.raises(RuntimeError, match="active lifecycle operation"):
        rebuild.fence_and_teardown_service_runtime(_service(), platform="docker")


def test_tenant_and_admin_force_rebuild_paths_fail_closed_on_teardown_error():
    runtime_api = (ROOT / "services/api/runtime.py").read_text(encoding="utf-8")
    admin_api = (ROOT / "services/api/admin_services.py").read_text(encoding="utf-8")

    for source in (runtime_api, admin_api):
        assert "fence_and_teardown_service_runtime(" in source
        assert "record_force_rebuild_teardown_failure(" in source
        assert 'if teardown_error is not None:' in source
        assert '"FORCE_REBUILD_TEARDOWN_FAILED"' in source

    assert "start_service force_rebuild teardown warning" not in runtime_api
    assert "start_service force_rebuild teardown warning" not in admin_api
