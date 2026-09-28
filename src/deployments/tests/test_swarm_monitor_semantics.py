import unittest
from types import SimpleNamespace

from deployments.celery.schedules import _swarm_failure_details, _swarm_has_terminal_runtime_failure


class SwarmMonitorSemanticsTests(unittest.TestCase):
    def _task(self, *, state, desired_state="running", error="", message=""):
        return SimpleNamespace(
            task_id="task-1",
            desired_state=desired_state,
            state=state,
            node_id="node-1",
            node_name="manager",
            error=error,
            message=message,
            image="demo:r1@sha256:new",
        )

    def _state(self, *, tasks, replicas_desired=1, replicas_running=0, update_state=None):
        return SimpleNamespace(
            tasks=tuple(tasks),
            replicas_desired=replicas_desired,
            replicas_running=replicas_running,
            update_state=update_state,
            update_message="",
            service_image="demo:r1@sha256:new",
        )

    def test_pending_replacement_is_not_terminal(self):
        state = self._state(tasks=[self._task(state="pending")])
        self.assertFalse(_swarm_has_terminal_runtime_failure(state))

    def test_starting_replacement_is_not_terminal(self):
        state = self._state(tasks=[self._task(state="starting")])
        self.assertFalse(_swarm_has_terminal_runtime_failure(state))

    def test_terminal_failed_task_is_terminal(self):
        state = self._state(
            tasks=[self._task(
                state="failed",
                error="task: non-zero exit (1)",
                message="process exited with code 1",
            )]
        )
        self.assertTrue(_swarm_has_terminal_runtime_failure(state))

    def test_missing_desired_task_for_desired_replica_is_terminal(self):
        state = self._state(tasks=[], replicas_desired=1)
        self.assertTrue(_swarm_has_terminal_runtime_failure(state))

    def test_swarm_update_or_rollback_pause_is_not_terminal(self):
        for update_state in ("updating", "rollback_started", "rollback_paused"):
            with self.subTest(update_state=update_state):
                state = self._state(
                    tasks=[self._task(state="failed")],
                    update_state=update_state,
                )
                self.assertFalse(_swarm_has_terminal_runtime_failure(state))

    def test_failure_details_include_task_reason_and_runtime_logs(self):
        runtime = SimpleNamespace(
            service_logs=lambda name, tail=100: b"app exited unexpectedly\\n"
        )
        state = self._state(
            tasks=[self._task(
                state="failed",
                error="task: non-zero exit (1)",
                message="process exited with code 1",
            )]
        )
        details = _swarm_failure_details(runtime, "demo", state)

        self.assertEqual(details["tasks"][0]["error"], "task: non-zero exit (1)")
        self.assertEqual(details["tasks"][0]["image"], "demo:r1@sha256:new")
        self.assertIn("app exited unexpectedly", details["service_logs"])


if __name__ == "__main__":
    unittest.main()
