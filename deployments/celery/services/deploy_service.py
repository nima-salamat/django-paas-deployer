import logging
import traceback

from django.db.models import Q

from deploy.models import Deploy
from deploy.deployment_state import DjangoDeploymentState
from core.global_settings.config import default_ports
from deployments.core.deploy import Deploy as DeployFacade
from deployments.core.types import VolumeSpec
from deployments.core.manager.container_manager import Container
from services.models import Volume
from ..service_status import ServiceStateManager
from ..validators import DeploymentValidator
from ..helpers import DeploymentHelper, MockOrchestratorResult
from ..waiters import ContainerWaiter
from ..exceptions import InvalidServiceStateError, OrchestratorDeploymentError

logger = logging.getLogger(__name__)


class DeployService:
    """Orchestrates deployment execution flows coupled with state logging."""

    def execute(self, deploy_id: int) -> None:
        try:
            deploy_item = ServiceStateManager.lock_and_get_deployment(deploy_id)
        except InvalidServiceStateError as exc:
            logger.info("Skipped deploy execution for ID %s: %s", deploy_id, str(exc))
            return

        service_id = deploy_item.service.id
        container_name = deploy_item.service.get_docker_service_name()
        state_tracker = DjangoDeploymentState(deploy_item)

        if deploy_item.cancel_requested:
            state_tracker.finish(
                MockOrchestratorResult(
                    success=False,
                    stage="cancelled",
                    message="Deployment cancelled before execution.",
                    status="cancelled",
                )
            )
            ServiceStateManager.sync_legacy_stopped(service_id)
            return

        state_tracker.start()

        try:
            result = self._process_deployment(deploy_item, container_name, state_tracker)
            if getattr(result, "status", None) == "cancelled":
                ServiceStateManager.sync_legacy_stopped(service_id)
            else:
                ServiceStateManager.sync_legacy_success(service_id)
            logger.info("Successfully executed deploy cycle for container: %s", container_name)

        except Exception as exc:
            logger.error("Deployment critical failure on %s: %s", container_name, str(exc), exc_info=True)
            state_tracker.record_exception(exc, traceback.format_exc())
            if state_tracker.deploy.status not in {"failed", "cancelled"}:
                state_tracker.finish(
                    MockOrchestratorResult(
                        success=False,
                        stage=getattr(exc, "stage", "deployment_failed"),
                        message=str(exc) or "Deployment failed.",
                        error=str(exc),
                    )
                )
            ServiceStateManager.sync_legacy_failure(service_id)
            raise

    def _process_deployment(self, deploy_item: Deploy, container_name: str, state_tracker: DjangoDeploymentState):
        platform = deploy_item.service.plan.platform
        dockerfile_text = DeploymentHelper.get_dockerfile_text(platform)

        DeploymentValidator.validate_for_deploy(deploy_item, dockerfile_text)

        if DeploymentHelper.is_restart_only(deploy_item, container_name):
            logger.info("Fast-path conditions met. Restarting existing container: %s", container_name)
            Container(container_name).start()
            restart_result = MockOrchestratorResult(
                success=True,
                stage="deployment_completed",
                message="Existing container containerized instance restarted successfully."
            )
            state_tracker.finish(restart_result)
            result = restart_result
        else:
            logger.info("Full orchestration required. Building image for: %s", container_name)
            result = self._execute_orchestrator(deploy_item, container_name, platform, dockerfile_text, state_tracker)

        if getattr(result, "status", None) != "cancelled":
            ContainerWaiter.wait_until_running(container_name, timeout=30)
        return result

    def _execute_orchestrator(
        self,
        deploy_item: Deploy,
        container_name: str,
        platform: str,
        dockerfile_text: str,
        state_tracker: DjangoDeploymentState
    ):
        port = default_ports.get(platform)
        service = deploy_item.service

        cfg = getattr(deploy_item, "config", None) or {}
        if not isinstance(cfg, dict):
            cfg = {}

        environment = dict(cfg.get("env") or cfg.get("environment") or {})
        server_type = (
            getattr(deploy_item, "server_type", None)
            or cfg.get("server_type")
            or getattr(service, "server_type", None)
        )
        entry_point = (
            getattr(deploy_item, "entry_point", None)
            or cfg.get("entry_point")
            or getattr(service, "entry_point", None)
        )
        celery = bool(
            getattr(deploy_item, "celery", False)
            or cfg.get("celery")
            or getattr(service, "celery", False)
        )
        celery_beat = bool(
            getattr(deploy_item, "celery_beat", False)
            or cfg.get("celery_beat")
            or getattr(service, "celery_beat", False)
        ) and celery

        deployer = DeployFacade(
            name=container_name,
            tag=deploy_item.version,
            zip_filename=deploy_item.zip_file.path,
            dockerfile_text=dockerfile_text,
            max_cpu=service.plan.max_cpu,
            max_ram=service.plan.max_ram,
            networks=[(service.network.name, "bridge")],
            volumes=self._volume_specs(deploy_item),
            port=port,
            read_only=service.read_only,
            platform=platform,
            platform_type=service.plan.plan_type,
            event_sink=state_tracker.event_sink,
            deployment_id=deploy_item.id,
            environment=environment,
            server_type=server_type,
            celery=celery,
            celery_beat=celery_beat,
            entry_point=entry_point,
        )

        result = deployer.deploy_result()
        state_tracker.finish(result)

        if not result.success and result.status != "cancelled":
            raise OrchestratorDeploymentError(f"Orchestrator compilation failed: {result.message}")
        return result

    @staticmethod
    def _get_volumes_for_service(service):
        """Return all Volume objects attached to the given service."""
        service_id = str(service.id)
        q_legacy = Q(service=service)
        q_json = Q(service_attachments__has_key=service_id)
        return Volume.objects.filter(q_legacy | q_json).distinct()

    @staticmethod
    def _volume_specs(deploy_item: Deploy) -> list[VolumeSpec]:
        specs = []
        for volume in DeployService._get_volumes_for_service(deploy_item.service):
            attrs = deploy_item.service.service_attachments.get(str(volume.id), {})
            bind = attrs.get('bind', volume.default_bind)
            mode = attrs.get('mode', volume.default_mode)
            specs.append(VolumeSpec(
                source=volume.name,
                target=bind,
                mode=mode,
                mount_type="volume",
                size_mb=volume.size_mb,
            ))
        return specs