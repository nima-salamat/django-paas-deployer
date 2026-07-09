import logging
from deploy.deployment_state import DjangoDeploymentState
from deployments.core.deploy import Deploy as DeployFacade
from deployments.core.manager.container_manager import Container
from ..service_status import ServiceStateManager
from ..helpers import MockOrchestratorResult
from ..waiters import ContainerWaiter
from ..exceptions import InvalidServiceStateError

logger = logging.getLogger(__name__)


class StopService:
    """Orchestrates container stop actions, logging events if an active deploy plan is bound."""

    def execute(self, service_id: int) -> None:
        try:
            service = ServiceStateManager.lock_and_start_stopping(service_id)
        except InvalidServiceStateError as exc:
            logger.info("Skipped stop execution for service ID %s: %s", service_id, str(exc))
            return

        container_name = service.get_docker_service_name()
        
        # Use state tracker if a current deployment reference exists
        state_tracker = DjangoDeploymentState(service.selected_deploy) if service.selected_deploy else None

        try:
            if Container.container_is_running(container_name):
                logger.info("Dispatching stop request for container: %s", container_name)
                DeployFacade.stop_container(container_name)
                ContainerWaiter.wait_until_stopped(container_name, timeout=5)
            else:
                logger.info("Container %s already matches terminal state: STOPPED.", container_name)

            if state_tracker:
                stop_result = MockOrchestratorResult(
                    success=True, stage="cleanup", message="Container processing environment gracefully stopped."
                )
                state_tracker.finish(stop_result)

            ServiceStateManager.sync_legacy_stopped(service_id)

        except Exception as exc:
            logger.error("Stop execution runtime failure on %s: %s", container_name, str(exc), exc_info=True)
            if state_tracker:
                fail_result = MockOrchestratorResult(
                    success=False, stage="deployment_failed", message=f"Stop processing error: {str(exc)}"
                )
                state_tracker.finish(fail_result)
                
            ServiceStateManager.sync_legacy_failure(service_id)
            raise