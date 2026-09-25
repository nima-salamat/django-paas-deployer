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
