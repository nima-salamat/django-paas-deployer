from deployments.core.swarm import SwarmRuntime


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
