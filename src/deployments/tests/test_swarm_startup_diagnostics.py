from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from deployments.core.swarm import SwarmRuntime


def test_task_logs_are_collected_from_the_exact_failed_container():
    runtime = object.__new__(SwarmRuntime)
    runtime.client = MagicMock()
    container = MagicMock()
    container.logs.return_value = b"current task: /usr/local/bin/apache2-foreground: not found\\n"
    runtime.client.containers.get.return_value = container
    task = SimpleNamespace(task_id="task-123", container_id="container-123")

    logs = runtime._task_logs_for_failure(task)

    assert logs == "current task: /usr/local/bin/apache2-foreground: not found\\n"
    runtime.client.containers.get.assert_called_once_with("container-123")
    container.logs.assert_called_once_with(
        stdout=True,
        stderr=True,
        timestamps=True,
        tail=200,
    )


def test_swarm_task_state_preserves_exit_code_and_resource_limits():
    runtime = object.__new__(SwarmRuntime)
    runtime.client = MagicMock()
    service = MagicMock()
    service.tasks.return_value = [{
        "ID": "task-137",
        "DesiredState": "running",
        "NodeID": None,
        "Status": {
            "State": "failed",
            "Err": "task: non-zero exit (137)",
            "Message": "process exited with code 137",
            "Timestamp": "2026-11-02T03:30:39Z",
            "ContainerStatus": {
                "ContainerID": "container-137",
                "ExitCode": 137,
            },
        },
        "Spec": {
            "ContainerSpec": {"Image": "wordpress:test"},
            "Resources": {
                "Limits": {"MemoryBytes": 536870912, "NanoCPUs": 1000000000}
            },
        },
    }]

    task = runtime._task_states(service)[0]

    assert task.exit_code == 137
    assert task.memory_limit_bytes == 536870912
    assert task.nano_cpus == 1000000000


def test_exit_137_is_classified_as_oom_only_when_docker_confirms_it():
    runtime = object.__new__(SwarmRuntime)
    failure = runtime._startup_process_failure(
        service_name="app-wordpress",
        task_id="task-137",
        exit_code=137,
        task_diagnostics={
            "exit_code": 137,
            "oom_killed": True,
            "memory_limit_bytes": 536870912,
            "memory_limit_swap_bytes": None,
            "error": "",
        },
        service_logs="old task: wp-cron.php returned 200",
        task_logs="PHP Fatal error: Allowed memory size exhausted; token=do-not-expose",
        expected_image="wordpress:test",
        task_error="task: non-zero exit (137)",
        task_message="process exited with code 137",
    )

    assert failure is not None
    assert failure.code == "SWARM_TASK_OOM_KILLED"
    assert failure.details["failure_reason"] == "exit_137_oom_confirmed"
    assert failure.details["oom_status"] == "confirmed"
    assert failure.details["log_evidence_source"] == "task_container"
    assert "wp-cron.php" not in failure.technical_message
    assert "do-not-expose" not in failure.details["task_logs"]


def test_exit_137_without_oom_confirmation_is_reported_conservatively():
    runtime = object.__new__(SwarmRuntime)
    failure = runtime._startup_process_failure(
        service_name="app-wordpress",
        task_id="task-137",
        exit_code=137,
        task_diagnostics={
            "exit_code": 137,
            "oom_killed": False,
            "memory_limit_bytes": 1073741824,
            "error": "",
        },
        service_logs="",
        task_logs="",
        expected_image="wordpress:test",
        task_error="task: non-zero exit (137)",
    )

    assert failure is not None
    assert failure.code == "SWARM_TASK_EXIT_137"
    assert failure.details["oom_status"] == "not_confirmed"
    assert failure.details["failure_reason"] == "exit_137_oom_unconfirmed"
    assert failure.details["exit_status_interpretation"].startswith("commonly SIGKILL")
    assert "does not prove the signal or an OOM event" in failure.technical_message


def test_exit_127_diagnostic_surfaces_missing_executable_and_redacts_secrets():
    runtime = object.__new__(SwarmRuntime)
    failure = runtime._startup_process_failure(
        service_name="app-wordpress",
        task_id="task-127",
        exit_code=127,
        task_diagnostics={
            "error": "",
            "path": "/usr/local/bin/docker-ensure-installed.sh",
            "args": [
                "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
                "/usr/local/bin/apache2-foreground",
            ],
            "entrypoint": ["/usr/local/bin/docker-ensure-installed.sh"],
            "cmd": [
                "/usr/local/bin/passdeployer-wordpress-entrypoint.sh",
                "/usr/local/bin/apache2-foreground",
            ],
        },
        service_logs=(
            "2026-10-08T23:51:38Z ERROR stale-service-log "
            "/usr/local/bin/passdeployer-wordpress-entrypoint.sh: not found"
        ),
        task_logs=(
            "2026-10-08T23:20:38Z ERROR token=do-not-expose "
            "/usr/local/bin/apache2-foreground: not found"
        ),
        expected_image="app-wordpress:test",
        task_error="",
        task_message="task: non-zero exit (127)",
    )

    assert failure is not None
    assert failure.code == "SWARM_APPLICATION_PROCESS_EXITED"
    assert "/usr/local/bin/docker-ensure-installed.sh" in failure.technical_message
    assert "/usr/local/bin/apache2-foreground: not found" in failure.technical_message
    assert "do-not-expose" not in failure.technical_message
    assert "stale-service-log" not in failure.technical_message
    assert failure.details["log_evidence_source"] == "task_container"
    assert failure.details["matching_service_log_lines"]
    assert failure.details["matching_service_log_lines"][0].endswith(
        "/usr/local/bin/apache2-foreground: not found"
    )


def test_task_logs_fall_back_to_persisted_stream_when_remote_node_is_unreachable():
    runtime = object.__new__(SwarmRuntime)
    runtime.client = MagicMock()
    runtime.client.containers.get.side_effect = RuntimeError("container is on another node")

    stream_query = MagicMock()
    stream_query.values_list.return_value = [77]
    entry_query = MagicMock()
    entry_values = MagicMock()
    entry_values.__getitem__.return_value = [{
        "ts": None,
        "stream": "stderr",
        "message": "database connection failed",
    }]
    entry_query.order_by.return_value.values.return_value = entry_values

    with (
        patch("logs.models.ServiceLogStream.objects.using") as stream_using,
        patch("logs.models.ServiceLogEntry.objects.using") as entry_using,
    ):
        stream_using.return_value.filter.return_value = stream_query
        entry_using.return_value.filter.return_value = entry_query

        task = SimpleNamespace(task_id="task-remote", container_id="a" * 64)
        logs = runtime._task_logs_for_failure(task)

    assert "[stderr] database connection failed" in logs
    stream_using.assert_called_once()
    stream_using.return_value.filter.assert_called_once_with(
        container_id="a" * 64
    )
    entry_using.assert_called_once()
