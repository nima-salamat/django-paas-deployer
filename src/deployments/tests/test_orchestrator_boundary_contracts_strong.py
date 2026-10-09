"""Strong orchestrator boundary tests for deployment activation and safety."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from deployments.common.exceptions import DeploymentCancelled, DeploymentError
from deployments.core.orchestrator import DeploymentOrchestrator
from deployments.core.types import DeploymentConfig, NetworkSpec


def make_config(**overrides):
    values = dict(
        name="demo-app",
        tag="v1",
        zip_path="/tmp/source.zip",
        dockerfile_template="FROM python:3.12",
        max_cpu=1.0,
        max_ram=512,
        networks=[NetworkSpec(name="demo-network")],
        volumes=[],
        port=8000,
        read_only=False,
        platform="python",
        platform_type="app",
    )
    values.update(overrides)
    return DeploymentConfig(**values)


def fake_swarm_state(name="demo-app-web"):
    return SimpleNamespace(
        name=name,
        service_id="swarm-service-1",
        replicas_desired=1,
        replicas_running=1,
        tasks=[SimpleNamespace(task_id="task-1")],
    )


class OrchestratorBoundaryContracts(unittest.TestCase):
    def test_expired_lifecycle_deadline_is_rejected_before_any_pipeline_work(self):
        deadline = SimpleNamespace(expired=lambda: True)
        orchestrator = DeploymentOrchestrator(deadline=deadline)

        with self.assertRaises(DeploymentError) as ctx:
            orchestrator.deploy(make_config())

        self.assertEqual(ctx.exception.code, "DEPLOYMENT_DEADLINE_EXCEEDED")
        self.assertEqual(ctx.exception.stage, "timeout")

    def test_cancel_check_translates_timeout_and_user_cancellation_separately(self):
        timeout_orchestrator = DeploymentOrchestrator(cancel_check=lambda: "timeout")
        with self.assertRaises(DeploymentCancelled) as timeout_ctx:
            timeout_orchestrator._check_cancelled()
        self.assertEqual(timeout_ctx.exception.stage, "timeout")
        self.assertEqual(timeout_ctx.exception.code, "DEPLOYMENT_TIMEOUT")

        cancelled_orchestrator = DeploymentOrchestrator(cancel_check=lambda: True)
        with self.assertRaises(DeploymentCancelled) as cancel_ctx:
            cancelled_orchestrator._check_cancelled()
        self.assertEqual(cancel_ctx.exception.stage, "cancelled")
        self.assertEqual(cancel_ctx.exception.code, "DEPLOYMENT_CANCELLED")

    def test_swarm_activation_happens_only_after_runtime_cleanup(self):
        events = []
        state = fake_swarm_state()
        runtime = MagicMock()
        runtime._last_apply_recovery = {}
        runtime.apply_processes.return_value = {"web": state}
        runtime.cleanup_legacy_containers.side_effect = lambda service_id: events.append("legacy_cleanup") or []
        runtime.cleanup_stale_process_services.side_effect = lambda **kwargs: events.append("stale_cleanup") or ([], [])

        orchestrator = DeploymentOrchestrator(
            runtime_backend="swarm",
            swarm_runtime=runtime,
            activation_callback=lambda: events.append("activate"),
        )
        orchestrator._journal_resource = MagicMock()
        orchestrator._check_cancelled = MagicMock()
        orchestrator.logger.info = MagicMock()

        result = orchestrator._deploy_swarm_runtime(
            make_config(labels={"service.id": "service-1"}),
            image_ref="demo-app:v1",
        )

        self.assertTrue(result.success)
        self.assertEqual(events, ["legacy_cleanup", "activate"])
        runtime.apply_processes.assert_called_once()
        orchestrator._journal_resource.assert_called_once()

    def test_swarm_critical_cleanup_failure_blocks_activation(self):
        state = fake_swarm_state()
        runtime = MagicMock()
        runtime._last_apply_recovery = {}
        runtime.apply_processes.return_value = {"web": state}
        runtime.cleanup_legacy_containers.side_effect = RuntimeError("cleanup exploded")

        activated = []
        orchestrator = DeploymentOrchestrator(
            runtime_backend="swarm",
            swarm_runtime=runtime,
            activation_callback=lambda: activated.append(True),
        )
        orchestrator._journal_resource = MagicMock()
        orchestrator._check_cancelled = MagicMock()
        orchestrator.logger.info = MagicMock()

        with self.assertRaises(DeploymentError) as ctx:
            orchestrator._deploy_swarm_runtime(
                make_config(labels={"service.id": "service-1"}),
                image_ref="demo-app:v1",
            )

        self.assertEqual(ctx.exception.stage, "cleanup")
        self.assertEqual(ctx.exception.code, "DEPLOYMENT_CRITICAL_CLEANUP_FAILED")
        self.assertEqual(activated, [])

    def test_swarm_runtime_failure_captures_recovery_context_from_exception_details(self):
        state = fake_swarm_state()
        runtime = MagicMock()
        runtime._last_apply_recovery = {"attempted": True}
        runtime.apply_processes.side_effect = DeploymentError(
            "apply failed",
            stage="swarm_apply",
            details={"swarm_recovery": {"stale_service_names": ["old-web"]}},
        )

        orchestrator = DeploymentOrchestrator(
            runtime_backend="swarm",
            swarm_runtime=runtime,
        )

        with self.assertRaises(DeploymentError):
            orchestrator._deploy_swarm_runtime(
                make_config(labels={"service.id": "service-1"}),
                image_ref="demo-app:v1",
            )

        self.assertEqual(
            orchestrator._swarm_recovery_context,
            {"stale_service_names": ["old-web"]},
        )

    def test_swarm_success_result_exposes_primary_task_and_service_replica_counts(self):
        state = fake_swarm_state()
        runtime = MagicMock()
        runtime._last_apply_recovery = {}
        runtime.apply_processes.return_value = {"web": state}
        runtime.cleanup_legacy_containers.return_value = []

        orchestrator = DeploymentOrchestrator(runtime_backend="swarm", swarm_runtime=runtime)
        orchestrator._journal_resource = MagicMock()
        orchestrator._check_cancelled = MagicMock()
        orchestrator.logger.info = MagicMock()

        result = orchestrator._deploy_swarm_runtime(
            make_config(),
            image_ref="demo-app:v1",
        )

        self.assertEqual(result.details["runtime"], "docker-swarm")
        self.assertEqual(result.details["replicas"], {"web": 1})
        self.assertEqual(result.details["primary_task"], "task-1")
        self.assertEqual(result.image_ref, "demo-app:v1")
        self.assertEqual(result.container_name, "demo-app")


if __name__ == "__main__":
    unittest.main()
