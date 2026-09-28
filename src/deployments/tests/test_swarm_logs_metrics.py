import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from deployments.management.commands.run_log_collector import Command
from deployments.core.swarm import SwarmRuntime


class FakeSwarmLogService:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.name = "demo"

    def logs(self, **kwargs):
        return iter(self._chunks)


class FakeContainers:
    def __init__(self, container):
        self.container = container

    def get(self, container_id):
        return self.container


class FakeServiceCollection:
    def __init__(self, service):
        self.service = service

    def get(self, name):
        return self.service


class FakeClient:
    def __init__(self, service, container=None):
        self.services = FakeServiceCollection(service)
        self.containers = FakeContainers(container) if container else None

    def info(self):
        return {"Swarm": {"NodeID": "node-1"}}


class SwarmLogAndMetricsTests(unittest.TestCase):
    def test_swarm_catch_up_consumes_generator_instead_of_persisting_repr(self):
        collector = Command()
        collector._persist_batch = MagicMock()

        service = SimpleNamespace(pk="svc-1")
        policy = SimpleNamespace(max_bytes_per_second=1024 * 1024)
        stream = SimpleNamespace(last_persisted_ts=None)
        rate = SimpleNamespace(allow=lambda n: True)

        docker_service = FakeSwarmLogService(
            [
                b"2026-09-29T02:44:47.123456789Z hello from swarm\n",
                b"2026-09-29T02:44:48.123456789Z second line\n",
            ]
        )

        Command._catch_up(
            collector,
            docker_service,
            stream,
            service,
            policy,
            "collector-1",
            rate,
        )

        collector._persist_batch.assert_called_once()
        lines = collector._persist_batch.call_args.args[-1]
        messages = [item["message"] for item in lines]
        self.assertEqual(messages, ["hello from swarm", "second line"])
        self.assertNotIn("generator object", " ".join(messages))

    def test_cpu_percent_uses_two_samples(self):
        first = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 1000,
                "online_cpus": 2,
            }
        }
        second = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 300},
                "system_cpu_usage": 2000,
                "online_cpus": 2,
            }
        }
        self.assertEqual(SwarmRuntime._cpu_percent(first, second), 40.0)

    def test_memory_percent_works_with_cgroup_usage_and_limit(self):
        sample = {"memory_stats": {"usage": 256, "limit": 1024}}
        self.assertEqual(SwarmRuntime._memory_percent(sample), 25.0)

    def test_service_stats_returns_real_swarm_cpu_and_memory(self):
        image = "demo:r1@sha256:new"
        docker_service = FakeSwarmLogService([])
        docker_service.id = "service-id"
        docker_service.attrs = {
            "Version": {"Index": 7},
            "Spec": {
                "Mode": {"Replicated": {"Replicas": 1}},
                "TaskTemplate": {
                    "ContainerSpec": {"Image": image},
                    }
            },
            "UpdateStatus": {},
        }
        docker_service.tasks = lambda filters=None: [{
            "ID": "task-1",
            "DesiredState": "running",
            "NodeID": "node-1",
            "Status": {
                "State": "running",
                "ContainerStatus": {"ContainerID": "container-1"},
            },
            "Spec": {"ContainerSpec": {"Image": image}},
        }]

        container = MagicMock()
        container.status = "running"
        container.stats.side_effect = [
            {
                "cpu_stats": {
                    "cpu_usage": {"total_usage": 100},
                    "system_cpu_usage": 1000,
                    "online_cpus": 2,
                },
                "memory_stats": {"usage": 256, "limit": 1024},
            },
            {
                "cpu_stats": {
                    "cpu_usage": {"total_usage": 300},
                    "system_cpu_usage": 2000,
                    "online_cpus": 2,
                },
                "memory_stats": {"usage": 256, "limit": 1024},
            },
        ]

        runtime = SwarmRuntime(
            FakeClient(docker_service, container=container)
        )
        result = runtime.service_stats("demo")

        self.assertTrue(result["running"])
        self.assertTrue(result["metrics_available"])
        self.assertEqual(result["cpu"], 40.0)
        self.assertEqual(result["memory"], 25.0)

    def test_service_stats_reports_unavailable_metrics_as_none_not_zero(self):
        docker_service = FakeSwarmLogService([])
        docker_service.id = "service-id"
        docker_service.attrs = {
            "Version": {"Index": 7},
            "Spec": {
                "Mode": {"Replicated": {"Replicas": 1}},
                "TaskTemplate": {
                    "ContainerSpec": {"Image": "demo:r1@sha256:new"},
                },
            },
            "UpdateStatus": {},
        }
        docker_service.tasks = lambda filters=None: [{
            "ID": "task-1",
            "DesiredState": "running",
            "NodeID": "node-2",
            "Status": {"State": "running"},
            "Spec": {"ContainerSpec": {"Image": "demo:r1@sha256:new"}},
        }]

        runtime = SwarmRuntime(
            FakeClient(docker_service, container=None)
        )
        result = runtime.service_stats("demo")

        self.assertFalse(result["metrics_available"])
        self.assertIsNone(result["cpu"])
        self.assertIsNone(result["memory"])
        self.assertEqual(
            result["metrics_reason"],
            "task_container_not_available_on_this_docker_node",
        )


if __name__ == "__main__":
    unittest.main()
