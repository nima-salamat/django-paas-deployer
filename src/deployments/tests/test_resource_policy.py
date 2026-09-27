from types import SimpleNamespace

from deployments.common.resource_policy import build_limits, runtime_limits, worker_count


def test_static_build_policy_uses_operator_defaults(monkeypatch, settings):
    monkeypatch.setattr("deployments.common.resource_policy._operator", lambda key, default: default)
    out = build_limits(SimpleNamespace(max_cpu=4, max_ram=4096))
    assert out["mode"] == "static"
    assert out["cpu"] == 1.0
    assert out["memory_mb"] == 1024


def test_plan_build_policy_can_be_enabled_server_side(monkeypatch, settings):
    def op(key, default):
        if key == "build.resource_mode":
            return "plan"
        return default
    monkeypatch.setattr("deployments.common.resource_policy._operator", op)
    out = build_limits(SimpleNamespace(max_cpu=2.5, max_ram=2048))
    assert out["mode"] == "plan"
    assert out["cpu"] == 2.5
    assert out["memory_mb"] == 2048


def test_plan_build_policy_still_has_operator_ceiling(monkeypatch, settings):
    def op(key, default):
        if key == "build.resource_mode": return "plan"
        if key == "build.max_cpu": return 2.0
        if key == "build.max_ram_mb": return 1024
        return default
    monkeypatch.setattr("deployments.common.resource_policy._operator", op)
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
