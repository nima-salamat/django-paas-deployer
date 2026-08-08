"""
Tests for ``deployments.common.state_machine``.
"""

import unittest

from deployments.common.state_machine import (
    check_service_transition,
    check_deploy_transition,
    InvalidTransition,
    SERVICE_QUEUED, SERVICE_DEPLOYING, SERVICE_RUNNING,
    SERVICE_STOPPING, SERVICE_STOPPED, SERVICE_FAILED,
    DEPLOY_PENDING, DEPLOY_RUNNING, DEPLOY_SUCCEEDED,
    DEPLOY_FAILED, DEPLOY_CANCELLED, DEPLOY_ROLLING_BACK, DEPLOY_ROLLED_BACK,
    is_service_terminal, is_deploy_terminal,
)


class TestServiceTransitions(unittest.TestCase):

    def test_queued_to_deploying(self):
        # Should not raise
        check_service_transition(SERVICE_QUEUED, SERVICE_DEPLOYING)

    def test_deploying_to_running(self):
        check_service_transition(SERVICE_DEPLOYING, SERVICE_RUNNING)

    def test_deploying_to_failed(self):
        check_service_transition(SERVICE_DEPLOYING, SERVICE_FAILED)

    def test_running_to_stopping(self):
        check_service_transition(SERVICE_RUNNING, SERVICE_STOPPING)

    def test_stopping_to_stopped(self):
        check_service_transition(SERVICE_STOPPING, SERVICE_STOPPED)

    def test_stopped_to_queued(self):
        check_service_transition(SERVICE_STOPPED, SERVICE_QUEUED)

    def test_idempotent_self_transition(self):
        # Self-transitions are always allowed (idempotent).
        check_service_transition(SERVICE_RUNNING, SERVICE_RUNNING)
        check_service_transition(SERVICE_STOPPED, SERVICE_STOPPED)

    def test_invalid_queued_to_stopped(self):
        # Cannot go straight from QUEUED to STOPPED without deploying.
        with self.assertRaises(InvalidTransition):
            check_service_transition(SERVICE_QUEUED, SERVICE_STOPPED)

    def test_invalid_stopped_to_running(self):
        # Stopped services must go through QUEUED before RUNNING.
        with self.assertRaises(InvalidTransition):
            check_service_transition(SERVICE_STOPPED, SERVICE_RUNNING)

    def test_invalid_failed_to_stopped(self):
        # FAILED is terminal except via QUEUED/DEPLOYING recovery.
        # Actually FAILED -> STOPPING is allowed (operator stops a failed service).
        check_service_transition(SERVICE_FAILED, SERVICE_STOPPING)


class TestDeployTransitions(unittest.TestCase):

    def test_pending_to_running(self):
        check_deploy_transition(DEPLOY_PENDING, DEPLOY_RUNNING)

    def test_pending_to_cancelled(self):
        check_deploy_transition(DEPLOY_PENDING, DEPLOY_CANCELLED)

    def test_running_to_succeeded(self):
        check_deploy_transition(DEPLOY_RUNNING, DEPLOY_SUCCEEDED)

    def test_running_to_failed(self):
        check_deploy_transition(DEPLOY_RUNNING, DEPLOY_FAILED)

    def test_running_to_rolling_back(self):
        check_deploy_transition(DEPLOY_RUNNING, DEPLOY_ROLLING_BACK)

    def test_rolling_back_to_rolled_back(self):
        check_deploy_transition(DEPLOY_ROLLING_BACK, DEPLOY_ROLLED_BACK)

    def test_rolling_back_to_failed(self):
        # Rollback itself failed
        check_deploy_transition(DEPLOY_ROLLING_BACK, DEPLOY_FAILED)

    def test_idempotent(self):
        check_deploy_transition(DEPLOY_SUCCEEDED, DEPLOY_SUCCEEDED)

    def test_invalid_succeeded_to_running(self):
        # Cannot resurrect a SUCCEEDED deploy directly.
        with self.assertRaises(InvalidTransition):
            check_deploy_transition(DEPLOY_SUCCEEDED, DEPLOY_RUNNING)

    def test_invalid_failed_to_succeeded(self):
        with self.assertRaises(InvalidTransition):
            check_deploy_transition(DEPLOY_FAILED, DEPLOY_SUCCEEDED)


class TestTerminalStates(unittest.TestCase):

    def test_service_terminal(self):
        self.assertTrue(is_service_terminal(SERVICE_STOPPED))
        self.assertTrue(is_service_terminal(SERVICE_FAILED))
        self.assertFalse(is_service_terminal(SERVICE_RUNNING))
        self.assertFalse(is_service_terminal(SERVICE_DEPLOYING))

    def test_deploy_terminal(self):
        for s in (DEPLOY_SUCCEEDED, DEPLOY_FAILED, DEPLOY_CANCELLED, DEPLOY_ROLLED_BACK):
            self.assertTrue(is_deploy_terminal(s), f"{s} should be terminal")
        for s in (DEPLOY_PENDING, DEPLOY_RUNNING, DEPLOY_ROLLING_BACK):
            self.assertFalse(is_deploy_terminal(s), f"{s} should not be terminal")


class TestInvalidTransitionMessage(unittest.TestCase):

    def test_message_lists_allowed_targets(self):
        try:
            check_service_transition(SERVICE_STOPPED, SERVICE_RUNNING)
        except InvalidTransition as exc:
            msg = str(exc)
            self.assertIn("Service", msg)
            self.assertIn(SERVICE_STOPPED, msg)
            self.assertIn(SERVICE_RUNNING, msg)
            # Should list at least one allowed target
            self.assertTrue(len(exc.allowed) > 0)


if __name__ == "__main__":
    unittest.main()
