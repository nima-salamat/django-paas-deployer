from dataclasses import replace
import docker
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from django.test import override_settings

from deployments.common.exceptions import DeploymentError
from deployments.core.orchestrator import DeploymentOrchestrator
from deployments.core.swarm import (
    SwarmRuntime,
    compile_compose_service,
    _process_resource_limits,
    _validate_replicas,
)
from deployments.core.types import DeploymentConfig, NetworkSpec, EndpointSpec, VolumeSpec


class _FakeService:
    def __init__(self, *, image, tasks, update_state=None, update_message=None, version=7):
        self.id = "service-id"
        self.name = "demo"
        self.version = version
        self.attrs = {
            "Version": {"Index": version},
            "Spec": {
                "Mode": {"Replicated": {"Replicas": 1}},
                "TaskTemplate": {
                    "ContainerSpec": {"Image": image},
                },
            },
        }
        if update_state:
            self.attrs["UpdateStatus"] = {
                "State": update_state,
                "Message": update_message or "",
            }
        self._tasks = list(tasks)
        self._logs = [b"application traceback\n"]
        self.removed = False

    def reload(self):
        return self

    def tasks(self, filters=None):
        return list(self._tasks)

    def logs(self, **kwargs):
        return iter(self._logs)

    def remove(self):
        self.removed = True


class _FakeServices:
    def __init__(self, service):
        self.service = service

    def get(self, name):
        return self.service


class _FakeAPI:
    def __init__(self):
        self.calls = []

    def _url(self, path, resource):
        return path.format(resource)

    def _post_json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return object()

    def _result(self, response, json=False):
        return {"Warnings": []}


class _FakeClient:
    def __init__(self, service):
        self.services = _FakeServices(service)
        self.api = _FakeAPI()



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

    def test_read_only_swarm_service_gets_writable_runtime_tmpfs(self):
        spec = compile_compose_service(
            _config(read_only=True), image_ref="demo:r1"
        )
        self.assertEqual(
            spec["services"]["demo"]["tmpfs"],
            [{"target": "/run", "size": 16 * 1024 * 1024, "mode": 0o1777}],
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

    def test_create_kwargs_materialize_read_only_runtime_tmpfs(self):
        config = _config(read_only=True)
        spec = compile_compose_service(config, image_ref="demo:r1")
        runtime = SwarmRuntime.__new__(SwarmRuntime)
        with patch.object(runtime, "_apply_local_volume_pin", return_value=[]):
            kwargs = runtime._create_kwargs(config, image_ref="demo:r1", compose_spec=spec)
        tmpfs_mounts = [mount for mount in kwargs["mounts"] if mount.get("Type") == "tmpfs"]
        self.assertEqual(len(tmpfs_mounts), 1)
        self.assertEqual(tmpfs_mounts[0]["Target"], "/run")
        self.assertEqual(tmpfs_mounts[0]["TmpfsOptions"]["SizeBytes"], 16 * 1024 * 1024)

    def test_create_kwargs_adds_ready_app_service_dns_alias(self):
        config = _config(
            labels={
                "service.id": "svc-1",
                "deployment.id": "dep-1",
                "process.name": "web",
                "application.id": "app-1",
                "application.service": "mariadb",
            }
        )
        spec = compile_compose_service(config, image_ref="demo:r1")
        runtime = SwarmRuntime.__new__(SwarmRuntime)

        with patch.object(runtime, "_apply_local_volume_pin", return_value=[]):
            kwargs = runtime._create_kwargs(
                config,
                image_ref="demo:r1",
                compose_spec=spec,
            )

        self.assertEqual(len(kwargs["networks"]), 1)
        attachment = kwargs["networks"][0]
        self.assertEqual(attachment["Target"], "net-demo")
        self.assertEqual(attachment["Aliases"], ["mariadb"])

    def test_create_kwargs_adds_ready_app_database_dns_alias(self):
        config = _config(
            labels={
                "service.id": "svc-1",
                "deployment.id": "dep-1",
                "process.name": "database",
                "application.id": "app-1",
                "application.service": "mariadb",
            }
        )
        spec = compile_compose_service(config, image_ref="mariadb:11.8.9")
        runtime = SwarmRuntime.__new__(SwarmRuntime)

        with patch.object(runtime, "_apply_local_volume_pin", return_value=[]):
            kwargs = runtime._create_kwargs(
                config,
                image_ref="mariadb:11.8.9",
                compose_spec=spec,
            )

        self.assertEqual(len(kwargs["networks"]), 1)
        attachment = kwargs["networks"][0]
        self.assertEqual(attachment["Target"], "net-demo")
        self.assertEqual(attachment["Aliases"], ["mariadb"])

    def test_create_kwargs_keeps_ready_app_alias_off_proxy_network(self):
        config = _config(
            labels={
                "service.id": "svc-1",
                "deployment.id": "dep-1",
                "process.name": "web",
                "application.id": "app-1",
                "application.service": "wordpress",
            },
        )
        config = replace(
            config,
            networks=[
                NetworkSpec(name="net-demo", driver="overlay", internal=True, attachable=True),
                NetworkSpec(name="proxy_net", driver="overlay", internal=False, attachable=True),
            ],
        )
        spec = compile_compose_service(config, image_ref="demo:r1")
        runtime = SwarmRuntime.__new__(SwarmRuntime)

        with patch.object(runtime, "_apply_local_volume_pin", return_value=[]):
            kwargs = runtime._create_kwargs(
                config,
                image_ref="demo:r1",
                compose_spec=spec,
            )

        aliases_by_network = {
            attachment["Target"]: attachment["Aliases"]
            for attachment in kwargs["networks"]
        }
        self.assertEqual(aliases_by_network["net-demo"], ["wordpress"])
        self.assertEqual(aliases_by_network["proxy_net"], [])

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

    def test_ensure_network_creates_overlay_when_swarm_is_active(self):
        client = MagicMock()
        client.info.return_value = {
            "Swarm": {
                "LocalNodeState": "active",
                "ControlAvailable": True,
                "NodeID": "node-1",
            }
        }
        network = MagicMock()
        network.attrs = {"Driver": "overlay"}
        network.id = "network-1"
        client.networks.get.side_effect = docker.errors.NotFound("missing")
        client.networks.create.return_value = network

        runtime = SwarmRuntime(client)
        self.assertEqual(runtime.ensure_network("net-demo"), "network-1")
        client.networks.create.assert_called_once_with(
            "net-demo",
            driver="overlay",
            attachable=True,
            labels={"managed-by": "django-paas-deployer"},
            check_duplicate=True,
        )

    def test_ensure_network_migrates_empty_owned_legacy_bridge_network(self):
        client = MagicMock()
        client.info.return_value = {
            "Swarm": {
                "LocalNodeState": "active",
                "ControlAvailable": True,
                "NodeID": "node-1",
            }
        }
        legacy = MagicMock()
        legacy.attrs = {
            "Driver": "bridge",
            "Labels": {"managed-by": "django-paas-deployer"},
            "Containers": {},
        }
        migrated = MagicMock()
        migrated.id = "network-overlay-1"
        migrated.attrs = {"Driver": "overlay"}
        client.networks.get.return_value = legacy
        client.networks.create.return_value = migrated

        runtime = SwarmRuntime(client)
        self.assertEqual(runtime.ensure_network("net-demo"), "network-overlay-1")
        legacy.remove.assert_called_once()
        client.networks.create.assert_called_once_with(
            "net-demo",
            driver="overlay",
            attachable=True,
            labels={"managed-by": "django-paas-deployer"},
            check_duplicate=True,
        )

    def test_ensure_network_refuses_attached_legacy_bridge_network(self):
        client = MagicMock()
        client.info.return_value = {
            "Swarm": {
                "LocalNodeState": "active",
                "ControlAvailable": True,
                "NodeID": "node-1",
            }
        }
        legacy = MagicMock()
        legacy.attrs = {
            "Driver": "bridge",
            "Labels": {"managed-by": "django-paas-deployer"},
            "Containers": {"container-1": {}},
        }
        client.networks.get.return_value = legacy

        runtime = SwarmRuntime(client)
        with self.assertRaises(DeploymentError) as ctx:
            runtime.ensure_network("net-demo")
        self.assertEqual(ctx.exception.code, "SWARM_NETWORK_DRIVER_MISMATCH")
        legacy.remove.assert_not_called()

    def test_rejects_more_than_one_replica(self):
        with self.assertRaises(Exception):
            _validate_replicas(2)

    @override_settings(DEPLOYMENT_DOMAIN="deploy.echonode.website")
    def test_legacy_port_without_endpoint_gets_public_route_and_proxy_network(self):
        config = _config(public_host=None, endpoints=[])
        spec = compile_compose_service(config, image_ref="demo:r1")
        service = spec["services"]["demo"]
        labels = service["deploy"]["labels"]
        self.assertEqual(labels["traefik.http.routers.demo-http.rule"], "Host(`demo.deploy.echonode.website`)")
        self.assertIn("proxy_net", service["networks"])

    @override_settings(DEPLOYMENT_DOMAIN="deploy.echonode.website")
    def test_legacy_public_endpoint_uses_same_host_and_web_entrypoint(self):
        config = _config(
            public_host=None,
            endpoints=[EndpointSpec(
                name="http", target_port=8000, exposure="public", protocol="https", hostname="", tls=True
            )],
        )
        orchestrator = DeploymentOrchestrator.__new__(DeploymentOrchestrator)
        labels = orchestrator._endpoint_labels(config)
        self.assertEqual(
            labels["traefik.http.routers.demo-ep-0-http.rule"],
            "Host(`demo.deploy.echonode.website`)",
        )
        self.assertEqual(labels["traefik.http.routers.demo-ep-0-http.entrypoints"], "web")
        self.assertNotIn("traefik.http.routers.demo-ep-0-http.tls", labels)

    @override_settings(DEPLOYMENT_DOMAIN="deploy.echonode.website")
    def test_public_endpoint_without_hostname_uses_canonical_service_host(self):
        config = _config(public_host=None, endpoints=[EndpointSpec(
            name="http", target_port=8000, exposure="public", protocol="http", hostname=""
        )])
        spec = compile_compose_service(config, image_ref="demo:r1")
        labels = spec["services"]["demo"]["deploy"]["labels"]
        self.assertEqual(labels["traefik.http.routers.demo-http.rule"], "Host(`demo.deploy.echonode.website`)")

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

