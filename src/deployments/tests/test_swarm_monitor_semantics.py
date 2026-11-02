import unittest
from types import SimpleNamespace
from unittest.mock import patch

from deployments.celery.schedules import (
    _expected_swarm_process_replicas,
    _swarm_failure_details,
    _swarm_has_terminal_runtime_failure,
    _swarm_process_group_health,
)


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

    def test_failed_task_with_restart_policy_is_transient(self):
        state = self._state(
            tasks=[self._task(state="failed", error="exit 1")],
        )
        state.restart_condition = "on-failure"
        self.assertFalse(_swarm_has_terminal_runtime_failure(state))

    def test_missing_task_with_restart_policy_is_transient(self):
        state = self._state(tasks=[], replicas_desired=1)
        state.restart_condition = "on-failure"
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

    def test_process_group_requires_all_desired_replicas_for_every_process(self):
        states = {
            "app-web": self._state(
                tasks=[self._task(state="running"), self._task(state="running")],
                replicas_desired=2,
                replicas_running=2,
            ),
            "app-worker": self._state(
                tasks=[self._task(state="running"), self._task(state="starting")],
                replicas_desired=2,
                replicas_running=1,
            ),
        }

        class Runtime:
            def service_names_for_service(self, service_id):
                return ["app-web", "app-worker"]

            def inspect_service(self, name):
                return states[name]

        service = SimpleNamespace(
            pk="service-1",
            get_docker_service_name=lambda: "app-web",
        )
        ready, failed, observations = _swarm_process_group_health(Runtime(), service)

        self.assertFalse(ready)
        self.assertFalse(failed)
        self.assertEqual(observations[0]["replicas_desired"], 2)
        self.assertEqual(observations[0]["replicas_running"], 2)
        self.assertEqual(observations[1]["replicas_running"], 1)

    def test_process_group_is_ready_when_all_replicas_are_running(self):
        class Runtime:
            def service_names_for_service(self, service_id):
                return ["app-web", "app-worker"]

            def inspect_service(self, name):
                desired = 3 if name == "app-web" else 2
                return self_state(
                    tasks=[task(state="running") for _ in range(desired)],
                    replicas_desired=desired,
                    replicas_running=desired,
                )

        def task(*, state):
            return SimpleNamespace(desired_state="running", state=state)

        def self_state(*, tasks, replicas_desired, replicas_running):
            return SimpleNamespace(
                tasks=tuple(tasks),
                replicas_desired=replicas_desired,
                replicas_running=replicas_running,
                healthcheck_configured=False,
                update_state=None,
            )

        service = SimpleNamespace(
            pk="service-1",
            get_docker_service_name=lambda: "app-web",
        )
        ready, failed, observations = _swarm_process_group_health(Runtime(), service)

        self.assertTrue(ready)
        self.assertFalse(failed)
        self.assertEqual(len(observations), 2)

    def test_process_group_healthcheck_requires_healthy_replicas(self):
        class Runtime:
            def service_names_for_service(self, service_id):
                return ["app-worker"]

            def inspect_service(self, name):
                return SimpleNamespace(
                    tasks=(
                        SimpleNamespace(desired_state="running", state="running", health_status="healthy"),
                        SimpleNamespace(desired_state="running", state="running", health_status="starting"),
                    ),
                    replicas_desired=2,
                    replicas_running=2,
                    healthcheck_configured=True,
                    update_state=None,
                )

        service = SimpleNamespace(
            pk="service-1",
            get_docker_service_name=lambda: "app-web",
        )
        ready, failed, observations = _swarm_process_group_health(Runtime(), service)

        self.assertFalse(ready)
        self.assertFalse(failed)
        self.assertEqual(observations[0]["healthy_replicas"], 1)

    def test_expected_process_replicas_come_from_immutable_revision_graph(self):
        revision = SimpleNamespace(pk="revision-1")
        service = SimpleNamespace(
            pk="service-1",
            active_revision=revision,
            plan=SimpleNamespace(platform="django"),
            get_docker_service_name=lambda: "app-service",
        )
        graph = SimpleNamespace(processes=(
            SimpleNamespace(name="web", process_type="web", replicas=3, enabled=True),
            SimpleNamespace(name="worker", process_type="worker", replicas=2, enabled=True),
            SimpleNamespace(name="beat", process_type="worker", replicas=1, enabled=False),
        ))

        with patch(
            "deployments.core.runtime_graph.ServiceRuntimeGraph.from_revision",
            return_value=graph,
        ):
            expected = _expected_swarm_process_replicas(service)

        self.assertEqual(expected, {
            "app-service": 3,
            "app-service-worker": 2,
        })

    def test_process_group_detects_scale_down_against_revision_intent(self):
        revision = SimpleNamespace(pk="revision-1")
        service = SimpleNamespace(
            pk="service-1",
            active_revision=revision,
            plan=SimpleNamespace(platform="django"),
            get_docker_service_name=lambda: "app-service",
        )
        graph = SimpleNamespace(processes=(
            SimpleNamespace(name="web", process_type="web", replicas=3, enabled=True),
            SimpleNamespace(name="worker", process_type="worker", replicas=2, enabled=True),
        ))
        states = {
            "app-service": SimpleNamespace(
                tasks=(self._task(state="running"),),
                replicas_desired=1,
                replicas_running=1,
                healthcheck_configured=False,
                update_state=None,
            ),
            "app-service-worker": SimpleNamespace(
                tasks=(self._task(state="running"), self._task(state="running")),
                replicas_desired=2,
                replicas_running=2,
                healthcheck_configured=False,
                update_state=None,
            ),
        }

        class Runtime:
            def service_names_for_service(self, service_id):
                return ["app-service", "app-service-worker"]

            def inspect_service(self, name):
                return states[name]

        with patch(
            "deployments.core.runtime_graph.ServiceRuntimeGraph.from_revision",
            return_value=graph,
        ):
            ready, failed, observations = _swarm_process_group_health(
                Runtime(),
                service,
            )

        self.assertFalse(ready)
        self.assertFalse(failed)
        web = next(item for item in observations if item["name"] == "app-service")
        self.assertEqual(web["replicas_expected"], 3)
        self.assertEqual(web["replicas_desired"], 1)

    def test_missing_expected_process_is_not_reported_as_converged(self):
        revision = SimpleNamespace(pk="revision-1")
        service = SimpleNamespace(
            pk="service-1",
            active_revision=revision,
            plan=SimpleNamespace(platform="django"),
            get_docker_service_name=lambda: "app-service",
        )
        graph = SimpleNamespace(processes=(
            SimpleNamespace(name="web", process_type="web", replicas=1, enabled=True),
            SimpleNamespace(name="worker", process_type="worker", replicas=2, enabled=True),
        ))

        class Runtime:
            def service_names_for_service(self, service_id):
                return ["app-service"]

            def inspect_service(self, name):
                return SimpleNamespace(
                    tasks=(self._task(state="running"),),
                    replicas_desired=1,
                    replicas_running=1,
                    healthcheck_configured=False,
                    update_state=None,
                )

        runtime = Runtime()
        runtime._task = self._task
        with patch(
            "deployments.core.runtime_graph.ServiceRuntimeGraph.from_revision",
            return_value=graph,
        ):
            ready, failed, observations = _swarm_process_group_health(runtime, service)

        self.assertFalse(ready)
        self.assertFalse(failed)
        missing = next(item for item in observations if item["name"] == "app-service-worker")
        self.assertTrue(missing["missing"])
        self.assertEqual(missing["replicas_expected"], 2)

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
