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
