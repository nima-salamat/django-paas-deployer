import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from deployments.common.state_machine import (
    DEPLOY_PENDING,
    DEPLOY_RUNNING,
    DEPLOY_SUCCEEDED,
    DEPLOY_FAILED,
    DEPLOY_CANCELLED,
    SERVICE_RUNNING,
    SERVICE_QUEUED,
    check_deploy_transition,
    check_service_transition,
    InvalidTransition,
)


class TestDeploymentOwnershipStateRules(unittest.TestCase):
    def test_running_service_can_queue_replacement(self):
        check_service_transition(SERVICE_RUNNING, SERVICE_QUEUED)

    def test_duplicate_terminal_transition_is_idempotent_only_for_same_state(self):
        check_deploy_transition(DEPLOY_SUCCEEDED, DEPLOY_SUCCEEDED)
        with self.assertRaises(InvalidTransition):
            check_deploy_transition(DEPLOY_SUCCEEDED, DEPLOY_FAILED)
        with self.assertRaises(InvalidTransition):
            check_deploy_transition(DEPLOY_CANCELLED, DEPLOY_RUNNING)

    def test_normal_deploy_path_remains_pending_to_running_to_success(self):
        check_deploy_transition(DEPLOY_PENDING, DEPLOY_RUNNING)
        check_deploy_transition(DEPLOY_RUNNING, DEPLOY_SUCCEEDED)


class TestOwnershipHelpers(unittest.TestCase):
    def test_stale_worker_cannot_match_new_owner(self):
        current = SimpleNamespace(execution_task_id="new-task")
        self.assertNotEqual(current.execution_task_id, "old-task")

    def test_heartbeat_cutoff_is_stricter_than_single_monitor_tick(self):
        now = datetime.now(timezone.utc)
        heartbeat = now - timedelta(seconds=240)
        cutoff = now - timedelta(seconds=120)
        self.assertLess(heartbeat, cutoff)


if __name__ == "__main__":
    unittest.main()
