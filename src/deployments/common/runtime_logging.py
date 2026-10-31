"""Shared, operator-controlled Docker runtime log transport configuration.

Application containers never connect to the Django database or Redis directly.
Docker forwards their stdout/stderr to the local Fluent Bit Unix socket; Fluent
Bit batches and forwards records to the authenticated Django ingestion endpoint.
"""
from __future__ import annotations

import os


DEFAULT_FORWARD_SOCKET = "/run/passdeployer-logs/forward.sock"


def runtime_log_ingestion_enabled() -> bool:
    value = str(os.environ.get("LOG_INGEST_ENABLED", "1")).strip().lower()
    return value not in {"0", "false", "no", "off"}


def forward_socket_path() -> str:
    """Return the host-mounted Unix socket path used by Docker's Fluentd driver."""
    value = str(
        os.environ.get("LOG_FORWARD_SOCKET_PATH") or DEFAULT_FORWARD_SOCKET
    ).strip()
    if not value.startswith("/"):
        raise ValueError("LOG_FORWARD_SOCKET_PATH must be an absolute path")
    return value


def fluentd_log_driver_options() -> dict[str, str]:
    """Return bounded, non-blocking options shared by Docker and Swarm runtimes."""
    socket_path = forward_socket_path()
    buffer_size = str(os.environ.get("LOG_DOCKER_BUFFER_SIZE") or "256k").strip()
    try:
        record_limit = max(
            64, min(65536, int(os.environ.get("LOG_FLUENTD_BUFFER_LIMIT", "512")))
        )
    except (TypeError, ValueError):
        record_limit = 512

    return {
        "fluentd-address": f"unix://{socket_path}",
        "fluentd-async": "true",
        # Docker 29 parses this as a Go duration, not a bare millisecond count.
        "fluentd-async-reconnect-interval": "1s",
        "fluentd-buffer-limit": str(record_limit),
        # Moby's fluentd driver rejects values greater than math.MaxInt32.
        "fluentd-max-retries": "2147483647",
        "fluentd-sub-second-precision": "true",
        "labels": ",".join(
            (
                "managed-by",
                "passdeployer.service",
                "passdeployer.deployment",
                "passdeployer.process",
            )
        ),
        "tag": "passdeployer.{{.ID}}",
        # Docker's non-blocking mode prevents a stalled collector from
        # back-pressuring application stdout/stderr. The buffer is bounded.
        "mode": "non-blocking",
        "max-buffer-size": buffer_size,
    }


__all__ = [
    "DEFAULT_FORWARD_SOCKET",
    "forward_socket_path",
    "runtime_log_ingestion_enabled",
    "fluentd_log_driver_options",
]
