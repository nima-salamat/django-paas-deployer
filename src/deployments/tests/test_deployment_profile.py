from deployments.common.config import resolve_resource_limits, suggest_worker_count
from deployments.common.deployment_profile import normalize_profile


def test_tenant_resource_overrides_are_ignored():
    limits = resolve_resource_limits({
        "cpu": 8, "memory_mb": 4096, "pids_limit": 999999,
    }, plan_cpu=2, plan_ram_mb=1024)
    assert limits == {}


def test_nested_build_runtime_and_frontend_profiles_are_accepted():
    profile = normalize_profile(
        {
            "platform": "laravel",
            "frontend": {
                "package_manager": "npm",
                "build_command": "npm run build",
                "build_dir": "public/build",
            },
            "build": {"no_cache": True},
            "runtime": {"working_directory": "/var/www/html", "read_only": True},
            "resources": {"cpu": 1.5, "memory_mb": 768},
        },
        plan_cpu=2,
        plan_ram_mb=1024,
    )
    assert profile["build_options"]["no_cache"] is True
    assert profile["build_options"]["package_manager"] == "npm"
    assert profile["build_options"]["build_command"] == "npm run build"
    assert profile["build_options"]["build_dir"] == "public/build"
    assert profile["runtime_options"]["working_directory"] == "/var/www/html"
    assert profile["runtime_options"]["read_only"] is True
    assert profile["resource_limits"] == {}


def test_worker_suggestion_does_not_exceed_allocated_cpu_by_default():
    assert suggest_worker_count(0.5, 1024) == 1
    assert suggest_worker_count(1, 1024) == 1
    assert suggest_worker_count(2, 1024) == 2
    assert suggest_worker_count(8, 4096) == 8


def test_user_resources_and_worker_count_are_not_trusted():
    profile = normalize_profile({
        "resources": {"cpu": 999, "memory_mb": 999999},
        "resource_limits": {"cpu": 999},
        "worker_count": 128,
    }, plan_cpu=1, plan_ram_mb=512)
    assert profile["resource_limits"] == {}
    assert "worker_count" not in profile


def test_tenant_cannot_persist_or_execute_host_escape_hatches():
    profile = normalize_profile({
        "privileged": True,
        "devices": ["/dev/sda"],
        "volumes": {"/": {"bind": "/host"}},
        "network_mode": "host",
        "labels": {"managed-by": "evil"},
        "runtime_options": {"security_opt": ["seccomp=unconfined"]},
        "build_options": {"target": "builder", "network": "host", "build_args": {"SECRET": "x"}},
    })
    assert "privileged" not in profile
    assert "devices" not in profile
    assert "volumes" not in profile
    assert "network_mode" not in profile
    assert profile["build_options"] == {"target": "builder"}
