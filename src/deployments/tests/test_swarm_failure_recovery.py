import unittest
from unittest.mock import MagicMock, patch

from deployments.common.exceptions import DeploymentError
from deployments.core.orchestrator import DeploymentOrchestrator
from deployments.core.swarm import SwarmRuntime
from deployments.core.types import DeploymentConfig, NetworkSpec, EndpointSpec, VolumeSpec


class FakeService:
    def __init__(
        self,
        *,
        name="demo",
        image="demo:r1@sha256:new",
        tasks=(),
        update_state=None,
        update_message=None,
        version=7,
    ):
        self.id = "service-id"
        self.name = name
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
        self.removed = False

    def reload(self):
        return self

    def tasks(self, filters=None):
        return list(self._tasks)

    def logs(self, **kwargs):
        return iter([b"application traceback\n"])

    def remove(self):
        self.removed = True


class FakeServices:
    def __init__(self, service):
        self.service = service

    def get(self, name):
        return self.service


class FakeAPI:
    def __init__(self):
        self.calls = []

    def _url(self, path, resource):
        return path.format(resource)

    def _post_json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return object()

    def _result(self, response, json=False):
        return {"Warnings": []}


class FakeClient:
    def __init__(self, service):
        self.services = FakeServices(service)
        self.api = FakeAPI()


def config(**overrides):
    base = DeploymentConfig(
        name="demo",
        tag="r1",
        zip_path="/tmp/demo.zip",
        dockerfile_template="FROM python:3.12",
        max_cpu=1.0,
        max_ram=512,
        networks=[
            NetworkSpec(
                name="net-demo",
                driver="overlay",
                internal=True,
                attachable=True,
            )
        ],
        volumes=[VolumeSpec(source="vol-demo", target="/data")],
        port=8000,
        read_only=False,
        platform="python",
        platform_type="app",
        start_command="python app.py",
        environment={"APP_ENV": "production"},
        resource_limits={"cpu": 1.0, "memory_mb": 512},
        runtime_options={"placement_constraints": []},
        labels={"service.id": "svc-1", "deployment.id": "dep-1"},
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
    return base.__class__(**{**base.__dict__, **overrides})


class SwarmFailureRecoveryTests(unittest.TestCase):
    def test_failed_task_exposes_task_error_and_recent_logs(self):
        image = "demo:r1@sha256:new"
        service = FakeService(
            image=image,
            tasks=[
                {
                    "ID": "task-1",
                    "DesiredState": "running",
                    "Status": {
                        "State": "failed",
                        "Err": "task: non-zero exit (1)",
                        "Message": "process exited with code 1",
                    },
                    "Spec": {"ContainerSpec": {"Image": image}},
                }
            ],
            update_state="updating",
            update_message="update in progress",
        )
        runtime = SwarmRuntime(FakeClient(service))

        with self.assertRaises(DeploymentError) as ctx:
            runtime.wait_ready("demo", timeout=1, expected_image=image)

        exc = ctx.exception
        self.assertEqual(exc.code, "SWARM_TASK_FAILED")
        self.assertEqual(exc.stage, "swarm_startup")
        self.assertEqual(exc.details["task_id"], "task-1")
        self.assertIn("application traceback", exc.details["service_logs"])
        self.assertIn("non-zero exit (1)", exc.technical_message)

    def test_old_running_image_after_swarm_rollback_is_not_success(self):
        old_image = "demo:r0@sha256:old"
        new_image = "demo:r1@sha256:new"
        service = FakeService(
            image=old_image,
            tasks=[
                {
                    "ID": "old-task",
                    "DesiredState": "running",
                    "Status": {"State": "running", "Message": "started"},
                    "Spec": {"ContainerSpec": {"Image": old_image}},
                }
            ],
            update_state="rollback_completed",
            update_message="update rolled back",
        )
        runtime = SwarmRuntime(FakeClient(service))

        with self.assertRaises(DeploymentError) as ctx:
            runtime.wait_ready("demo", timeout=1, expected_image=new_image)

        self.assertEqual(ctx.exception.code, "SWARM_UPDATE_ROLLED_BACK")
        self.assertEqual(ctx.exception.details["expected_image"], new_image)

    def test_expected_running_image_is_required_for_readiness(self):
        image = "demo:r1@sha256:new"
        service = FakeService(
            image=image,
            tasks=[
                {
                    "ID": "task-1",
                    "DesiredState": "running",
                    "Status": {"State": "running", "Message": "started"},
                    "Spec": {"ContainerSpec": {"Image": image}},
                }
            ],
        )
        state = SwarmRuntime(FakeClient(service)).wait_ready(
            "demo",
            timeout=1,
            expected_image=image,
        )
        self.assertEqual(state.replicas_running, 1)
        self.assertEqual(state.service_image, image)
        self.assertEqual(state.tasks[0].image, image)

    def test_rollback_uses_engine_api_previous_spec(self):
        service = FakeService(
            tasks=[],
            update_state="updating",
            version=42,
        )
        client = FakeClient(service)
        runtime = SwarmRuntime(client)

        self.assertTrue(runtime.rollback_service("demo"))

        self.assertEqual(len(client.api.calls), 1)
        url, kwargs = client.api.calls[0]
        self.assertEqual(url, "/services/service-id/update")
        self.assertEqual(
            kwargs["params"],
            {"version": 42, "rollback": "previous"},
        )
        self.assertEqual(kwargs["data"], {})

    def test_duplicate_rollback_is_not_requested(self):
        service = FakeService(
            image="demo:r0@sha256:old",
            tasks=[],
            update_state="rollback_started",
            version=42,
        )
        client = FakeClient(service)

        self.assertFalse(SwarmRuntime(client).rollback_service("demo"))
        self.assertEqual(client.api.calls, [])

    def test_process_failure_records_recovery_for_all_successfully_mutated_services(self):
        runtime = SwarmRuntime.__new__(SwarmRuntime)
        runtime._last_apply_operation = None
        runtime._last_apply_recovery = {}
        runtime.assert_active = MagicMock()
        runtime.service_names_for_service = MagicMock(
            return_value=["demo", "demo-worker"]
        )

        cfg = config(
            runtime_options={
                "processes": [
                    {
                        "name": "web",
                        "process_type": "web",
                        "command": "python app.py",
                        "enabled": True,
                    },
                    {
                        "name": "worker",
                        "process_type": "worker",
                        "command": "python worker.py",
                        "enabled": True,
                    },
                ]
            }
        )

        def fake_apply(process_config, *, image_ref):
            runtime._last_apply_operation = {
                "name": process_config.name,
                "preexisting": True,
                "mutation_started": True,
                "mutation_succeeded": True,
            }
            if process_config.name == "demo-worker":
                raise DeploymentError(
                    "worker failed",
                    stage="swarm_startup",
                    code="SWARM_TASK_FAILED",
                )
            return FakeService()

        runtime.apply = fake_apply

        with self.assertRaises(DeploymentError) as ctx:
            runtime.apply_processes(cfg, image_ref="demo:r1@sha256:new")

        recovery = ctx.exception.details["swarm_recovery"]
        self.assertEqual(
            recovery["rollback_services"],
            ["demo", "demo-worker"],
        )
        self.assertEqual(recovery["remove_services"], [])

    def test_unsuccessful_existing_mutation_is_not_rollback_eligible(self):
        runtime = SwarmRuntime.__new__(SwarmRuntime)
        runtime._last_apply_operation = None
        runtime._last_apply_recovery = {}
        runtime.assert_active = MagicMock()
        runtime.service_names_for_service = MagicMock(return_value=["demo"])

        cfg = config(
            runtime_options={
                "processes": [
                    {
                        "name": "web",
                        "process_type": "web",
                        "command": "python app.py",
                        "enabled": True,
                    }
                ]
            }
        )

        def fake_apply(process_config, *, image_ref):
            runtime._last_apply_operation = {
                "name": process_config.name,
                "preexisting": True,
                "mutation_started": True,
                "mutation_succeeded": False,
            }
            raise RuntimeError("update failed before mutation")

        runtime.apply = fake_apply

        with self.assertRaises(RuntimeError):
            runtime.apply_processes(cfg, image_ref="demo:r1@sha256:new")

        recovery = runtime._last_apply_recovery
        self.assertEqual(recovery["rollback_services"], [])
        self.assertEqual(recovery["remove_services"], [])

    def test_first_deploy_new_services_are_removed_not_reported_as_rollback(self):
        orchestrator = DeploymentOrchestrator.__new__(DeploymentOrchestrator)
        orchestrator.logger = MagicMock()

        runtime = MagicMock()
        with patch(
            "deployments.core.orchestrator.SwarmRuntime",
            return_value=runtime,
        ):
            performed, failed = orchestrator._recover_swarm_mutations(
                {
                    "rollback_services": [],
                    "remove_services": ["demo", "demo-worker"],
                }
            )

        self.assertFalse(performed)
        self.assertFalse(failed)
        runtime.rollback_service.assert_not_called()
        self.assertEqual(runtime.remove.call_count, 2)

    def test_existing_processes_are_rolled_back_and_new_processes_removed(self):
        orchestrator = DeploymentOrchestrator.__new__(DeploymentOrchestrator)
        orchestrator.logger = MagicMock()

        runtime = MagicMock()
        runtime.rollback_service.return_value = True
        with patch(
            "deployments.core.orchestrator.SwarmRuntime",
            return_value=runtime,
        ):
            performed, failed = orchestrator._recover_swarm_mutations(
                {
                    "rollback_services": ["demo", "demo-worker"],
                    "remove_services": ["demo-scheduler"],
                }
            )

        self.assertTrue(performed)
        self.assertFalse(failed)
        self.assertEqual(runtime.rollback_service.call_count, 2)
        runtime.remove.assert_called_once_with("demo-scheduler")

    def test_recovery_runtime_init_failure_is_reported(self):
        orchestrator = DeploymentOrchestrator.__new__(DeploymentOrchestrator)
        orchestrator.logger = MagicMock()

        with patch(
            "deployments.core.orchestrator.SwarmRuntime",
            side_effect=RuntimeError("docker unavailable"),
        ):
            performed, failed = orchestrator._recover_swarm_mutations(
                {"rollback_services": ["demo"], "remove_services": []}
            )

        self.assertFalse(performed)
        self.assertTrue(failed)

    def test_deferred_stale_cleanup_is_best_effort(self):
        runtime = SwarmRuntime.__new__(SwarmRuntime)
        runtime.service_names_for_service = MagicMock(
            return_value=["demo", "demo-old"]
        )
        runtime.remove = MagicMock(return_value=None)

        removed, failures = runtime.cleanup_stale_process_services(
            service_id="svc-1",
            desired_service_names=["demo"],
        )

        self.assertEqual(removed, ["demo-old"])
        self.assertEqual(failures, [])

    def test_unexpected_swarm_process_exception_keeps_recovery_context(self):
        orchestrator = DeploymentOrchestrator.__new__(DeploymentOrchestrator)
        orchestrator.logger = MagicMock()

        runtime = MagicMock()
        runtime._last_apply_recovery = {
            "rollback_services": ["demo"],
            "remove_services": [],
        }
        runtime.apply_processes.side_effect = RuntimeError("unexpected runtime error")

        with patch(
            "deployments.core.orchestrator.SwarmRuntime",
            return_value=runtime,
        ):
            with self.assertRaises(RuntimeError):
                orchestrator._deploy_swarm_runtime(
                    config(),
                    image_ref="demo:r1@sha256:new",
                )

        self.assertEqual(
            orchestrator._swarm_recovery_context,
            runtime._last_apply_recovery,
        )


if __name__ == "__main__":
    unittest.main()
