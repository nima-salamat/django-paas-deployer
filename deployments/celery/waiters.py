import time
import logging
from deployments.core.manager.container_manager import Container
from .exceptions import ContainerTimeoutError

logger = logging.getLogger(__name__)


class ContainerWaiter:
    """Unified polling mechanism to verify container runtime states."""

    @classmethod
    def wait_for_status(cls, container_name: str, target_running: bool, timeout: int, interval: float = 0.5) -> None:
        iterations = int(timeout / interval)

        for _ in range(iterations):
            is_running = Container.container_is_running(container_name)
            if is_running == target_running:
                return
            time.sleep(interval)

        state_msg = "running" if target_running else "stopped"
        raise ContainerTimeoutError(
            f"Timeout exceeded ({timeout}s) waiting for container '{container_name}' to be {state_msg}."
        )

    @classmethod
    def wait_until_running(cls, container_name: str, timeout: int = 30) -> None:
        """Wait longer for heavier platforms (Node builds, PHP-FPM, DB init)."""
        cls.wait_for_status(container_name, target_running=True, timeout=timeout)

    @classmethod
    def wait_until_stopped(cls, container_name: str, timeout: int = 15) -> None:
        cls.wait_for_status(container_name, target_running=False, timeout=timeout)
