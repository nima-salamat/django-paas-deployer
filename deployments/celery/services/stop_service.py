"""
deployments/celery/services/stop_service.py
-------------------------------------------
Container stop service.

Key changes vs. legacy:
  * Acquires the per-service advisory lock so a stop cannot race with
    an in-progress deploy for the same Service.
  * Uses the unified ``InvalidServiceStateError`` from
    ``deployments.common.exceptions``.
  * Removes stopped containers after a successful stop so they don't
    accumulate on disk (legacy code only stopped, never removed —
    operators had to manually prune).  This is gated by a
    ``DEPLOYMENT_REMOVE_STOPPED_CONTAINERS`` setting (default True).
"""
from __future__ import annotations

import logging

from deploy.deployment_state import DjangoDeploymentState  # type: ignore
from deployments.core.deploy import Deploy as DeployFacade
from deployments.core.manager.container_manager import Container
from deployments.core.state.locks import acquire_service_deployment_lock
from deployments.common.exceptions import InvalidServiceStateError

from ..service_status import ServiceStateManager
from ..helpers import MockOrchestratorResult
from ..waiters import ContainerWaiter

logger = logging.getLogger(__name__)


def _should_remove_stopped_containers() -> bool:
    try:
        from django.conf import settings  # type: ignore
        return bool(getattr(settings, "DEPLOYMENT_REMOVE_STOPPED_CONTAINERS", True))
    except Exception:
        return True


class StopService:
    """Orchestrates container stop actions, logging events if an active deploy plan is bound."""

    def execute(self, service_id: int) -> None:
        # Acquire the per-service advisory lock so a stop cannot race
        # with an in-progress deploy for the same Service.
        try:
            with acquire_service_deployment_lock(service_id):
                self._execute_locked(service_id)
        except InvalidServiceStateError as exc:
            logger.info("Skipped stop execution for service ID %s: %s", service_id, str(exc))
            return
        except Exception:
            logger.exception("Stop for service %s could not acquire deployment lock.", service_id)
            return

    def _execute_locked(self, service_id: int) -> None:
        try:
            service = ServiceStateManager.lock_and_start_stopping(service_id)
        except InvalidServiceStateError as exc:
            logger.info("Skipped stop execution for service ID %s: %s", service_id, str(exc))
            return

        container_name = service.get_docker_service_name()

        state_tracker = (
            DjangoDeploymentState(service.selected_deploy)
            if service.selected_deploy else None
        )

        try:
            if Container.container_is_running(container_name):
                logger.info("Dispatching stop request for container: %s", container_name)
                DeployFacade.stop_container(container_name)
                ContainerWaiter.wait_until_stopped(container_name, timeout=10)
            else:
                logger.info(
                    "Container %s already matches terminal state: STOPPED.",
                    container_name,
                )

            # Remove the stopped container so it doesn't accumulate on
            # disk.  Legacy code only stopped, leaving dozens of stopped
            # containers per service over time.
            if _should_remove_stopped_containers():
                try:
                    stopped = Container(container_name)
                    if stopped.exists():
                        stopped.remove()
                        logger.info(
                            "Removed stopped container '%s' to free disk.",
                            container_name,
                        )
                except Exception as cleanup_exc:
                    logger.warning(
                        "Failed to remove stopped container '%s': %s. "
                        "Container remains stopped but on disk.",
                        container_name, cleanup_exc,
                    )

            if state_tracker:
                stop_result = MockOrchestratorResult(
                    success=True, stage="cleanup",
                    message="Container processing environment gracefully stopped.",
                )
                state_tracker.finish(stop_result)

            ServiceStateManager.sync_legacy_stopped(service_id)

        except Exception as exc:
            logger.error(
                "Stop execution runtime failure on %s: %s",
                container_name, str(exc), exc_info=True,
            )
            if state_tracker:
                fail_result = MockOrchestratorResult(
                    success=False, stage="deployment_failed",
                    message=f"Stop processing error: {str(exc)}",
                )
                state_tracker.finish(fail_result)

            ServiceStateManager.sync_legacy_failure(service_id)
            raise
