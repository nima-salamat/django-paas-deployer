from types import SimpleNamespace

from deployments.common.resource_policy import build_limits, resolve_build_policy, runtime_limits, worker_count


def test_static_build_policy_uses_operator_defaults(monkeypatch, settings):
    import core.settings_service as svc
    monkeypatch.setattr(svc, "build_resource_mode", lambda: "static")
    monkeypatch.setattr(svc, "build_max_cpu", lambda: 1.0)
    monkeypatch.setattr(svc, "build_max_ram_mb", lambda: 1024)
    monkeypatch.setattr(svc, "build_pids_limit", lambda: 2048)
    monkeypatch.setattr(svc, "build_shm_mb", lambda: 64)
    out = build_limits(SimpleNamespace(max_cpu=4, max_ram=4096))
    assert out["mode"] == "static"
    assert out["cpu"] == 1.0
    assert out["memory_mb"] == 1024


def test_plan_build_policy_can_be_enabled_server_side(monkeypatch, settings):
    import core.settings_service as svc
    monkeypatch.setattr(svc, "build_resource_mode", lambda: "plan")
    monkeypatch.setattr(svc, "build_max_cpu", lambda: 8.0)
    monkeypatch.setattr(svc, "build_max_ram_mb", lambda: 8192)
    monkeypatch.setattr(svc, "build_pids_limit", lambda: 2048)
    monkeypatch.setattr(svc, "build_shm_mb", lambda: 64)
    out = build_limits(SimpleNamespace(max_cpu=2.5, max_ram=2048))
    assert out["mode"] == "plan"
    assert out["cpu"] == 2.5
    assert out["memory_mb"] == 2048


def test_plan_build_policy_still_has_operator_ceiling(monkeypatch, settings):
    import core.settings_service as svc
    monkeypatch.setattr(svc, "build_resource_mode", lambda: "plan")
    monkeypatch.setattr(svc, "build_max_cpu", lambda: 2.0)
    monkeypatch.setattr(svc, "build_max_ram_mb", lambda: 1024)
    monkeypatch.setattr(svc, "build_pids_limit", lambda: 2048)
    monkeypatch.setattr(svc, "build_shm_mb", lambda: 64)
    out = build_limits(SimpleNamespace(max_cpu=8, max_ram=8192))
    assert out["cpu"] == 2.0
    assert out["memory_mb"] == 1024


def test_resolve_build_policy_fills_missing_fields_from_authoritative_policy(monkeypatch):
    import deployments.common.resource_policy as policy

    canonical = {
        "cpu": 1.0,
        "memory_mb": 1024,
        "pids_limit": 2048,
        "shm_size_mb": 64,
        "mode": "static",
    }
    monkeypatch.setattr(policy, "build_limits", lambda plan=None: dict(canonical))
    assert policy.resolve_build_policy() == canonical
    assert policy.resolve_build_policy({}) == canonical
    partial = policy.resolve_build_policy({"cpu": 2})
    assert partial["cpu"] == 2.0
    assert partial["memory_mb"] == 1024
    assert partial["pids_limit"] == 2048
    assert partial["shm_size_mb"] == 64


def test_force_rebuild_is_not_a_resource_policy(monkeypatch):
    import deployments.common.resource_policy as policy

    monkeypatch.setattr(
        policy,
        "build_limits",
        lambda plan=None: {
            "cpu": 1.0,
            "memory_mb": 1024,
            "pids_limit": 2048,
            "shm_size_mb": 64,
            "mode": "static",
        },
    )
    import pytest
    with pytest.raises(ValueError, match="force_rebuild"):
        policy.resolve_build_policy({"force_rebuild": True})
