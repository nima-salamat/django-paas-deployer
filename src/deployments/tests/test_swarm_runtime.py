from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from deployments.common.exceptions import DeploymentError
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

    def test_wait_ready_failure_carries_task_and_service_logs(self):
        source = (SwarmRuntime.wait_ready).__doc__ or ""
        module = __import__("deployments.core.swarm", fromlist=["wait_ready"])
        text = Path(module.__file__).read_text(encoding="utf-8")
        self.assertIn('"service_logs": service_logs[-12000:]', text)
        self.assertIn("task_detail = task.error or task.message or task.state", text)

    def test_wait_ready_reports_task_exit_and_service_logs(self):
        image = "demo:r1@sha256:new"
        service = _FakeService(
            image=image,
            tasks=[{
                "ID": "task-1",
                "DesiredState": "running",
                "Status": {
                    "State": "failed",
                    "Err": "task: non-zero exit (1)",
                    "Message": "task: non-zero exit (1)",
                },
                "Spec": {"ContainerSpec": {"Image": image}},
            }],
            update_state="updating",
            update_message="update in progress",
        )
        runtime = SwarmRuntime(_FakeClient(service))
        with self.assertRaises(DeploymentError) as ctx:
            runtime.wait_ready("demo", timeout=1, expected_image=image)

        exc = ctx.exception
        self.assertEqual(exc.code, "SWARM_TASK_FAILED")
        self.assertEqual(exc.stage, "swarm_startup")
        self.assertEqual(exc.details["task_id"], "task-1")
        self.assertIn("application traceback", exc.details["service_logs"])
        self.assertIn("non-zero exit (1)", exc.technical_message)
        self.assertIn("expected_image", exc.technical_message)

    def test_wait_ready_rejects_success_from_old_image_after_rollback(self):
        old_image = "demo:r0@sha256:old"
        new_image = "demo:r1@sha256:new"
        service = _FakeService(
            image=old_image,
            tasks=[{
                "ID": "old-task",
                "DesiredState": "running",
                "Status": {"State": "running", "Message": "started"},
                "Spec": {"ContainerSpec": {"Image": old_image}},
            }],
            update_state="rollback_completed",
            update_message="update rolled back because the task failed",
        )
        runtime = SwarmRuntime(_FakeClient(service))
        with self.assertRaises(DeploymentError) as ctx:
            runtime.wait_ready("demo", timeout=1, expected_image=new_image)

        self.assertEqual(ctx.exception.code, "SWARM_UPDATE_ROLLED_BACK")
        self.assertEqual(ctx.exception.details["expected_image"], new_image)
        self.assertIn("application traceback", ctx.exception.details["service_logs"])

    def test_wait_ready_accepts_only_the_expected_running_image(self):
        image = "demo:r1@sha256:new"
        service = _FakeService(
            image=image,
            tasks=[{
                "ID": "task-1",
                "DesiredState": "running",
                "Status": {"State": "running", "Message": "started"},
                "Spec": {"ContainerSpec": {"Image": image}},
            }],
        )
        runtime = SwarmRuntime(_FakeClient(service))
        state = runtime.wait_ready("demo", timeout=1, expected_image=image)
        self.assertEqual(state.replicas_running, 1)
        self.assertEqual(state.service_image, image)
        self.assertEqual(state.tasks[0].image, image)

    def test_rollback_service_uses_engine_api_previous_spec(self):
        image = "demo:r1@sha256:new"
        service = _FakeService(
            image=image,
            tasks=[],
            update_state="updating",
            version=42,
        )
        client = _FakeClient(service)
        runtime = SwarmRuntime(client)

        self.assertTrue(runtime.rollback_service("demo"))

        self.assertEqual(len(client.api.calls), 1)
        url, kwargs = client.api.calls[0]
        self.assertEqual(url, "/services/service-id/update")
        self.assertEqual(kwargs["params"], {"version": 42, "rollback": "previous"})
        self.assertEqual(kwargs["data"], {})

    def test_rollback_service_does_not_issue_duplicate_rollback(self):
        service = _FakeService(
            image="demo:r0@sha256:old",
            tasks=[],
            update_state="rollback_started",
            version=42,
        )
        client = _FakeClient(service)
        runtime = SwarmRuntime(client)

        self.assertFalse(runtime.rollback_service("demo"))
        self.assertEqual(client.api.calls, [])

    def test_apply_processes_records_all_mutated_services_for_recovery(self):
        config = _config(
            runtime_options={
                "processes": [
                    {"name": "web", "process_type": "web", "command": "python app.py", "enabled": True},
                    {"name": "worker", "process_type": "worker", "command": "python worker.py", "enabled": True},
                ]
            }
        )
        runtime = SwarmRuntime.__new__(SwarmRuntime)
        runtime._last_apply_operation = None
        runtime.assert_active = MagicMock()
        runtime.service_names_for_service = MagicMock(return_value=["demo", "demo-worker"])

        def fake_apply(process_config, *, image_ref):
            runtime._last_apply_operation = {
                "name": process_config.name,
                "preexisting": True,
                "mutation_started": True,
                "mutation_succeeded": True,
            }
            if process_config.name == "demo-worker":
                raise DeploymentError("worker failed", stage="swarm_startup", code="SWARM_TASK_FAILED")
            return _FakeService(
                image=image_ref,
                tasks=[],
            )

        runtime.apply = fake_apply

        with self.assertRaises(DeploymentError) as ctx:
            runtime.apply_processes(config, image_ref="demo:r1@sha256:new")

        recovery = ctx.exception.details["swarm_recovery"]
        self.assertEqual(
            recovery["rollback_services"],
            ["demo", "demo-worker"],
        )
        self.assertEqual(recovery["remove_services"], [])
        self.assertEqual(
            [item["name"] for item in recovery["operations"]],
            ["demo", "demo-worker"],
        )

    def test_first_deploy_process_failure_marks_new_services_for_removal(self):
        config = _config(
            runtime_options={
                "processes": [
                    {"name": "web", "process_type": "web", "command": "python app.py", "enabled": True},
                    {"name": "worker", "process_type": "worker", "command": "python worker.py", "enabled": True},
                ]
            }
        )
        runtime = SwarmRuntime.__new__(SwarmRuntime)
        runtime._last_apply_operation = None
        runtime.assert_active = MagicMock()
        runtime.service_names_for_service = MagicMock(return_value=[])

        def fake_apply(process_config, *, image_ref):
            runtime._last_apply_operation = {
                "name": process_config.name,
                "preexisting": False,
                "mutation_started": True,
                "mutation_succeeded": True,
            }
            if process_config.name == "demo-worker":
                raise DeploymentError("worker failed", stage="swarm_startup", code="SWARM_TASK_FAILED")
            return _FakeService(image=image_ref, tasks=[])

        runtime.apply = fake_apply

        with self.assertRaises(DeploymentError) as ctx:
            runtime.apply_processes(config, image_ref="demo:r1@sha256:new")

        recovery = ctx.exception.details["swarm_recovery"]
        self.assertEqual(recovery["rollback_services"], [])
        self.assertEqual(
            recovery["remove_services"],
            ["demo", "demo-worker"],
        )

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

