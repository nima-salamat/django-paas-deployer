from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from deployments.core.swarm import (
    SwarmRuntime,
    compile_compose_service,
    _process_resource_limits,
    _validate_replicas,
)
from deployments.core.types import DeploymentConfig, NetworkSpec, EndpointSpec, VolumeSpec


def _config(**overrides):
    base = DeploymentConfig(
        name="demo",
        tag="r1",
        zip_path="/tmp/demo.zip",
        dockerfile_template="FROM python:3.12",
        max_cpu=1.0,
        max_ram=512,
        networks=[NetworkSpec(name="net-demo", driver="overlay", internal=True, attachable=True)],
        volumes=[VolumeSpec(source="vol-demo", target="/data")],
        port=8000,
        read_only=False,
        platform="python",
        platform_type="app",
        start_command="python app.py",
        environment={"APP_ENV": "production"},
        resource_limits={"cpu": 1.0, "memory_mb": 512},
        runtime_options={"placement_constraints": ["node.labels.region == eu"]},
        labels={"service.id": "svc-1", "deployment.id": "dep-1", "process.name": "web"},
        public_host="demo.deploy.example.com",
        endpoints=[
            EndpointSpec(
                name="http",
                target_port=8000,
                exposure="public",
                protocol="http",
                hostname="demo.deploy.example.com",
            )
        ],
    )
    return replace(base, **overrides)


class SwarmRuntimeCompilerTests(unittest.TestCase):
    def test_compiles_one_replica_stack_shape(self):
        spec = compile_compose_service(_config(), image_ref="demo:r1")
        service = spec["services"]["demo"]
        self.assertEqual(service["deploy"]["replicas"], 1)
        self.assertEqual(service["deploy"]["placement"]["constraints"], ["node.labels.region == eu"])
        self.assertEqual(service["image"], "demo:r1")
        self.assertEqual(service["environment"], ["APP_ENV=production"])
        self.assertEqual(service["volumes"], ["vol-demo:/data:rw"])
        labels = service["deploy"]["labels"]
        self.assertEqual(labels["passdeployer.service"], "svc-1")
        self.assertEqual(labels["passdeployer.process"], "web")
        self.assertEqual(labels["traefik.swarm.network"], "proxy_net")
        self.assertEqual(
            labels["traefik.http.services.demo-http.loadbalancer.server.port"],
            "8000",
        )


    def test_compiles_healthcheck_resource_and_process_placement(self):
        config = _config(
            runtime_options={
                "healthcheck": {
                    "test": "python -c 'print(1)'",
                    "interval": "10s",
                    "timeout": "4s",
                    "retries": 5,
                    "start_period": "15s",
                },
                "placement_constraints": ["node.labels.region == eu"],
            },
            resource_limits={"cpu": 1.5, "memory_mb": 768},
        )
        spec = compile_compose_service(config, image_ref="demo:r1")
        service = spec["services"]["demo"]
        self.assertEqual(
            service["healthcheck"],
            {
                "test": ["CMD-SHELL", "python -c 'print(1)'"],
                "interval": 10_000_000_000,
                "timeout": 4_000_000_000,
                "retries": 5,
                "start_period": 15_000_000_000,
            },
        )
        self.assertEqual(
            service["deploy"]["resources"]["limits"],
            {"cpus": "1.5", "memory": "768M"},
        )
        self.assertEqual(
            service["deploy"]["placement"]["constraints"],
            ["node.labels.region == eu"],
        )

    def test_process_resources_cannot_exceed_plan_cpu_or_memory(self):
        with self.assertRaises(Exception):
            _process_resource_limits(
                {"cpu": 1.0, "memory_mb": 512},
                {"cpu": 2.0},
            )
        with self.assertRaises(Exception):
            _process_resource_limits(
                {"cpu": 1.0, "memory_mb": 512},
                {"memory_mb": 1024},
            )

    def test_process_resources_can_refine_plan_within_ceiling(self):
        limits = _process_resource_limits(
            {"cpu": 2.0, "memory_mb": 1024},
            {"cpu": 1.5, "memory_mb": 768},
        )
        self.assertEqual(limits["cpu"], 1.5)
        self.assertEqual(limits["memory_mb"], 768)

    def test_create_kwargs_preserve_effective_start_command(self):
        config = _config(
            entry_point="python app.py --port 8000",
            start_command="ignored start command",
        )
        spec = compile_compose_service(config, image_ref="demo:r1")

        runtime = SwarmRuntime.__new__(SwarmRuntime)
        with patch.object(runtime, "_apply_local_volume_pin", return_value=["node.labels.region == eu"]):
            kwargs = runtime._create_kwargs(
                config,
                image_ref="demo:r1",
                compose_spec=spec,
            )

        self.assertNotIn("entrypoint", kwargs)
        self.assertEqual(kwargs["command"], ["/bin/sh", "-lc", "python app.py --port 8000"])
        self.assertNotIn("args", kwargs)

    def test_rejects_more_than_one_replica(self):
        with self.assertRaises(Exception):
            _validate_replicas(2)

    def test_compiles_multiple_public_http_endpoints(self):
        config = _config(
            endpoints=[
                EndpointSpec(
                    name="web",
                    target_port=8000,
                    exposure="public",
                    protocol="http",
                    hostname="demo.deploy.example.com",
                ),
                EndpointSpec(
                    name="api",
                    target_port=9000,
                    exposure="public",
                    protocol="http",
                    hostname="api.demo.deploy.example.com",
                    path="/v1",
                ),
            ]
        )
        spec = compile_compose_service(config, image_ref="demo:r1")
        labels = spec["services"]["demo"]["deploy"]["labels"]
        self.assertEqual(
            labels["traefik.http.services.demo-web.loadbalancer.server.port"],
            "8000",
        )
        self.assertEqual(
            labels["traefik.http.services.demo-api.loadbalancer.server.port"],
            "9000",
        )
        self.assertIn(
            "PathPrefix(` /v1 `)".replace(" ", ""),
            labels["traefik.http.routers.demo-api.rule"],
        )

    def test_compiles_udp_public_port(self):
        config = _config(
            endpoints=[
                EndpointSpec(
                    name="dns",
                    target_port=53,
                    published_port=3053,
                    exposure="public",
                    protocol="udp",
                )
            ]
        )
        spec = compile_compose_service(config, image_ref="demo:r1")
        self.assertEqual(
            spec["services"]["demo"]["ports"],
            [{"target": 53, "published": 3053, "protocol": "udp", "mode": "ingress"}],
        )

