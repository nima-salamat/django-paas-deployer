from dataclasses import replace
from types import SimpleNamespace
import unittest

from deployments.core.swarm import compile_compose_service, _validate_replicas
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

    def test_rejects_more_than_one_replica(self):
        with self.assertRaises(Exception):
            _validate_replicas(2)

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

