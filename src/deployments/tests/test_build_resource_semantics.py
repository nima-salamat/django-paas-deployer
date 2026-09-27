from types import SimpleNamespace


def test_build_cpu_is_mapped_to_relative_cpu_shares_not_hard_quota():
    import deployments.core.manager.image_manager as image_manager
    limits = image_manager._build_container_limits(policy={
        "cpu": 2.0,
        "memory_mb": 1024,
        "pids_limit": 2048,
        "shm_size_mb": 64,
        "mode": "static",
    })
    assert limits["cpushares"] == 2048
    assert limits["cpushares"] != 2.0
    assert "cpu_quota" not in limits
    assert "nano_cpus" not in limits


def test_base_image_timeout_is_the_same_setting_used_for_stale_recovery():
    from pathlib import Path
    settings_source = (Path(__file__).resolve().parents[2] / "core" / "settings_service.py").read_text(encoding="utf-8")
    assert "def base_image_timeout_minutes() -> int:" in settings_source
    assert "return base_image_timeout_minutes()" in settings_source
def test_runtime_policies_expose_canonical_base_image_timeout():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "celery" / "monitoring" / "policies.py").read_text(encoding="utf-8")
    assert '"base_image_timeout_minutes"' in source
    assert '"stale_base_build_minutes"' in source

def test_runtime_policies_expose_canonical_base_image_timeout(monkeypatch):
    import core.settings_service as svc
    monkeypatch.setattr(svc, "base_image_timeout_minutes", lambda: 41)
    monkeypatch.setattr(svc, "deploy_timeout_minutes", lambda: 10)
    import deployments.celery.monitoring.policies as policies
    out = policies.runtime_policies()
    assert out["base_image_timeout_minutes"] == 41
    assert out["stale_base_build_minutes"] == 41
