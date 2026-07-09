import time

from .exceptions import HealthCheckError
from .manager.container_manager import Container


class DockerHealthChecker:
    def __init__(self, logger=None):
        self.logger = logger

    def wait_until_healthy(self, container_name: str, *, timeout: int = 45, interval: float = 1.0):
        start = time.time()
        last_status = "unknown"

        while time.time() - start <= timeout:
            container = Container(container_name)
            status = container.status()
            last_status = status

            if status in {"running", "healthy"}:
                if self.logger:
                    self.logger.info(
                        "health_check",
                        f"Container '{container_name}' is {status}.",
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
            details={"container": container_name, "last_status": last_status, "timeout": timeout},
        )
