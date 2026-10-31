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

    with patch("logs.models.ServiceLogStream.objects.using") as stream_using, \\
         patch("logs.models.ServiceLogEntry.objects.using") as entry_using:
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
