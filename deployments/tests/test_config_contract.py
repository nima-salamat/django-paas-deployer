from deployments.core.types import DeploymentConfig


def test_deployment_config_accepts_server_build_resource_policy():
    cfg = DeploymentConfig(
        name="demo",
        tag="v1",
        zip_path="/tmp/demo.zip",
        dockerfile_template="FROM alpine:3.20",
        max_cpu=1.0,
        max_ram=512,
        networks=[],
        volumes=[],
        port=None,
        read_only=False,
        platform="docker",
        platform_type="APP",
        build_resource_policy={"cpu": 1.0, "memory_mb": 1024, "pids_limit": 2048},
    )
    assert cfg.build_resource_policy["cpu"] == 1.0


def test_url_handling_and_paths_are_scoped():
    from deployments.common.config import validate_platform_config
    report = validate_platform_config({
        "paths": {"document_root": "public", "static_dir": "public/build"},
        "url_handling": {"mode": "custom", "public_url": "https://example.com/app", "asset_url": "https://cdn.example.com/assets"},
    }, "laravel", project_paths={"public/index.php", "public/build/app.css"})
    assert report["normalized"]["document_root"] == "public"
    assert report["normalized"]["url_handling"]["mode"] == "custom"

def test_invalid_custom_path_does_not_fall_back_silently():
    from deployments.common.config import validate_platform_config
    import pytest
    with pytest.raises(ValueError):
        validate_platform_config({"document_root": "../../etc"}, "laravel", project_paths={"public/index.php"})


def test_platform_specific_contract_warnings_and_custom_urls():
    from deployments.common.config import validate_platform_config
    report = validate_platform_config({
        "static_dir": "dist",
        "url_handling": {"mode": "disabled"},
    }, "laravel")
    assert any("static_dir" in w for w in report["warnings"])
    assert report["normalized"]["url_handling"]["mode"] == "disabled"

def test_custom_url_rejects_shell_metacharacters():
    from deployments.common.config import validate_platform_config
    import pytest
    with pytest.raises(ValueError):
        validate_platform_config({"url_handling": {"mode": "custom", "asset_url": "https://x.test/;touch"}}, "laravel")
