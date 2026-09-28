import unittest
from unittest.mock import MagicMock, patch

from deployments.common.exceptions import DeploymentError
from deployments.core.orchestrator import DeploymentOrchestrator


class SwarmOrchestratorRecoveryTests(unittest.TestCase):
    def _orchestrator(self):
        orchestrator = DeploymentOrchestrator.__new__(DeploymentOrchestrator)
        orchestrator.logger = MagicMock()
        return orchestrator

    def test_recovery_rolls_back_existing_and_removes_new_services(self):
        orchestrator = self._orchestrator()
        runtime = MagicMock()
        runtime.rollback_service.return_value = True

        recovery = {
            "rollback_services": ["demo", "demo-worker"],
            "remove_services": ["demo-scheduler"],
        }

        with patch(
            "deployments.core.orchestrator.SwarmRuntime",
            return_value=runtime,
        ):
            performed, failed = orchestrator._recover_swarm_mutations(recovery)

        self.assertTrue(performed)
        self.assertFalse(failed)
        self.assertEqual(
            runtime.rollback_service.call_count,
            2,
        )
        runtime.remove.assert_called_once_with("demo-scheduler")

    def test_cleanup_only_does_not_report_rollback_performed(self):
        orchestrator = self._orchestrator()
        runtime = MagicMock()

        recovery = {
            "rollback_services": [],
            "remove_services": ["demo"],
        }

        with patch(
            "deployments.core.orchestrator.SwarmRuntime",
            return_value=runtime,
        ):
            performed, failed = orchestrator._recover_swarm_mutations(recovery)

        self.assertFalse(performed)
        self.assertFalse(failed)
        runtime.rollback_service.assert_not_called()
        runtime.remove.assert_called_once_with("demo")

    def test_failed_rollback_is_reported_without_removing_existing_service(self):
        orchestrator = self._orchestrator()
        runtime = MagicMock()
        runtime.rollback_service.side_effect = DeploymentError(
            "rollback failed",
            stage="rollback",
            code="SWARM_ROLLBACK_FAILED",
        )

        recovery = {
            "rollback_services": ["demo"],
            "remove_services": [],
        }

        with patch(
            "deployments.core.orchestrator.SwarmRuntime",
            return_value=runtime,
        ):
            performed, failed = orchestrator._recover_swarm_mutations(recovery)

        self.assertFalse(performed)
        self.assertTrue(failed)
        runtime.remove.assert_not_called()


if __name__ == "__main__":
    unittest.main()
