import time

from .exceptions import HealthCheckError
from .manager.container_manager import Container


class DockerHealthChecker:
    def __init__(self, logger=None):
        self.logger = logger

    def wait_until_healthy(
        self,
        container_name: str,
        *,
        timeout: int = 60,
        interval: float = 1.0,
        allow_running_without_healthcheck: bool = True,
    ):
        """
        Poll until the container is healthy or (optionally) simply running.

        Many platforms (Flask, Node, PHP, Go) do not ship a HEALTHCHECK
        instruction. In that case a container that reaches "running" is
        accepted so deployments do not fail spuriously.
        """
        start = time.time()
        last_status = "unknown"

        while time.time() - start <= timeout:
            container = Container(container_name)
            status = container.status()
            last_status = status

            if status == "healthy":
                if self.logger:
                    self.logger.info(
                        "health_check",
                        f"Container '{container_name}' is healthy.",
                        progress=90,
                        details={"container_status": status},
                    )
                return {"status": status}

            if status == "running" and allow_running_without_healthcheck:
                if self.logger:
                    self.logger.info(
                        "health_check",
                        f"Container '{container_name}' is running.",
                        progress=90,
                        details={"container_status": status},
                    )
                return {"status": status}

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
            },
        )
