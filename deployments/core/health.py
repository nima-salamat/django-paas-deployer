"""
deployments/core/health.py
--------------------------
Container health checker.

The legacy implementation accepted a single "running" status as success
for containers without a HEALTHCHECK.  This meant a process that started
and crashed 100ms later could be reported as a successful deploy if the
first poll happened to hit during those 100ms.

We now require N consecutive successful polls for non-HEALTHCHECK
containers.  HEALTHCHECK-enabled containers continue to require
``healthy`` (Docker itself already debounces that).
"""

from __future__ import annotations

import time

from deployments.common.exceptions import HealthCheckError
from .manager.container_manager import Container


# Number of consecutive "running" polls required before declaring a
# non-HEALTHCHECK container healthy.  With interval=1s, this gives ~3s
# of stability — enough to catch immediate-exit crashes.
DEFAULT_MIN_RUNNING_POLLS = 3


class DockerHealthChecker:
    def __init__(self, logger=None, *, min_running_polls: int = DEFAULT_MIN_RUNNING_POLLS):
        self.logger = logger
        self.min_running_polls = max(1, int(min_running_polls))

    def wait_until_healthy(
        self,
        container_name: str,
        *,
        timeout: int = 60,
        interval: float = 1.0,
        allow_running_without_healthcheck: bool = True,
    ) -> dict:
        """
        Poll until the container is healthy or (optionally) stably running.

        Behaviour:
          * If the container has a HEALTHCHECK, wait for ``healthy``.
          * If the container has no HEALTHCHECK and
            ``allow_running_without_healthcheck=True``, wait for
            ``min_running_polls`` consecutive ``running`` polls.
          * On ``unhealthy`` or timeout, raise ``HealthCheckError``.
        """
        start = time.time()
        last_status = "unknown"
        consecutive_running = 0
        has_healthcheck: bool | None = None

        while time.time() - start <= timeout:
            container = Container(container_name)
            status = container.status()
            last_status = status

            # Detect whether the container has a HEALTHCHECK by looking
            # at the inspect payload once.  ``status()`` returns
            # ``"running"`` for non-HEALTHCHECK containers, so we
            # inspect directly to find out.
            if has_healthcheck is None:
                info = container.inspect()
                state = (info or {}).get("State") or {}
                has_healthcheck = bool(state.get("Health"))

            if status == "healthy":
                if self.logger:
                    self.logger.info(
                        "health_check",
                        f"Container '{container_name}' is healthy.",
                        progress=90,
                        details={"container_status": status},
                    )
                return {"status": status, "healthcheck": True}

            if (
                status == "running"
                and allow_running_without_healthcheck
                and not has_healthcheck
            ):
                consecutive_running += 1
                if consecutive_running >= self.min_running_polls:
                    if self.logger:
                        self.logger.info(
                            "health_check",
                            f"Container '{container_name}' is running "
                            f"({consecutive_running} consecutive polls).",
                            progress=90,
                            details={
                                "container_status": status,
                                "consecutive_polls": consecutive_running,
                                "healthcheck": False,
                            },
                        )
                    return {
                        "status": status,
                        "healthcheck": False,
                        "consecutive_polls": consecutive_running,
                    }
                # Not enough consecutive polls yet — keep going.
                time.sleep(interval)
                continue

            # Reset the consecutive counter on any non-running status.
            consecutive_running = 0

            if status == "unhealthy":
                break

            if self.logger:
                self.logger.debug(
                    "health_check",
                    f"Waiting for container health; current status is {status}.",
                    progress=88,
                    details={"container_status": status},
                )
            time.sleep(interval)

        raise HealthCheckError(
            f"Container '{container_name}' did not become healthy before timeout.",
            details={
                "container": container_name,
                "last_status": last_status,
                "timeout": timeout,
                "has_healthcheck": has_healthcheck,
                "consecutive_running": consecutive_running,
                "required_consecutive": self.min_running_polls,
            },
        )
