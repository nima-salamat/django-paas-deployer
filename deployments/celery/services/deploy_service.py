import logging
import traceback
import json

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


def _parse_config(raw) -> dict:
    """Normalize Deploy.config whether stored as dict or JSON string."""
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str) and parsed.strip():
                parsed2 = json.loads(parsed)
                if isinstance(parsed2, dict):
                    return parsed2
        except Exception:
            pass
    return {}


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


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
                ServiceStateManager.sync_legacy_success(service_id, deploy_id=deploy_item.pk)
            logger.info("Successfully executed deploy cycle for container: %s", container_name)

        except Exception as exc:
            logger.error(
                "Deployment critical failure on %s: %s",
                container_name,
                str(exc),
                exc_info=True,
            )
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
            ServiceStateManager.sync_legacy_failure(service_id, deploy_id=deploy_item.pk)
            raise

    def _process_deployment(self, deploy_item: Deploy, container_name: str, state_tracker: DjangoDeploymentState):
        cfg = _parse_config(getattr(deploy_item, "config", None))
        platform = (
            str(cfg.get("platform") or "").lower().strip()
            or str(getattr(getattr(deploy_item.service, "plan", None), "platform", None) or "docker").lower().strip()
        )
        # Runtime image tags from Deploy.config (optional overrides)
        version_overrides = {
            k: cfg[k]
            for k in (
                "python_version",
                "django_python_version",
                "node_version",
                "php_version",
                "go_version",
                "dotnet_version",
                "nginx_version",
                "port",
                "build_dir",
            )
            if cfg.get(k) is not None and str(cfg.get(k)).strip() != ""
        }
        dockerfile_text = DeploymentHelper.get_dockerfile_text(
            platform, version_overrides=version_overrides or None
        )

        DeploymentValidator.validate_for_deploy(deploy_item, dockerfile_text)

        if DeploymentHelper.is_restart_only(deploy_item, container_name):
            logger.info("Fast-path conditions met. Restarting existing container: %s", container_name)
            Container(container_name).start()
            restart_result = MockOrchestratorResult(
                success=True,
                stage="deployment_completed",
                message="Existing container instance restarted successfully.",
            )
            state_tracker.finish(restart_result)
            result = restart_result
        else:
            logger.info("Full orchestration required. Building image for: %s", container_name)
            result = self._execute_orchestrator(
                deploy_item, container_name, platform, dockerfile_text, state_tracker
            )

        if getattr(result, "status", None) != "cancelled":
            # Django + Celery/supervisord needs more time to come up
            cfg = _parse_config(getattr(deploy_item, "config", None))
            use_celery = _as_bool(cfg.get("celery"))
            wait_timeout = 90 if use_celery or platform == "django" else 45
            ContainerWaiter.wait_until_running(container_name, timeout=wait_timeout)
        return result

    def _execute_orchestrator(
        self,
        deploy_item: Deploy,
        container_name: str,
        platform: str,
        dockerfile_text: str,
        state_tracker: DjangoDeploymentState,
    ):
        # Port: Deploy.config["port"] → platform default (SPA nginx = 80)
        raw_port = cfg.get("port")
        if raw_port is not None and str(raw_port).strip() != "":
            try:
                port = int(raw_port)
            except (TypeError, ValueError):
                port = default_ports.get(platform)
        else:
            port = default_ports.get(platform)
        service = deploy_item.service
        cfg = _parse_config(getattr(deploy_item, "config", None))

        environment = dict(cfg.get("env") or cfg.get("environment") or {})
        # Ensure all env values are strings (Docker requirement)
        environment = {str(k): str(v) for k, v in environment.items()}

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
        celery = _as_bool(
            getattr(deploy_item, "celery", False)
            or cfg.get("celery")
            or getattr(service, "celery", False)
        )
        celery_beat = _as_bool(
            getattr(deploy_item, "celery_beat", False)
            or cfg.get("celery_beat")
            or getattr(service, "celery_beat", False)
        ) and celery

        # Optional explicit celery app module, e.g. "config" or "myproject"
        celery_app = (
            cfg.get("celery_app")
            or cfg.get("celery_module")
            or None
        )

        # worker_count: default 1 unless user sets it in Deploy.config
        worker_count = 1
        raw_wc = (
            cfg.get("worker_count")
            or cfg.get("workers")
            or getattr(deploy_item, "worker_count", None)
            or getattr(service, "worker_count", None)
        )
        if raw_wc is not None:
            try:
                worker_count = max(1, int(raw_wc))
            except (TypeError, ValueError):
                worker_count = 1

        logger.info(
            "Orchestrator options for %s: platform=%s celery=%s celery_beat=%s "
            "server_type=%s entry_point=%s celery_app=%s worker_count=%s",
            container_name,
            platform,
            celery,
            celery_beat,
            server_type,
            entry_point,
            celery_app,
            worker_count,
        )

        networks = []
        if getattr(service, "network", None) is not None and getattr(service.network, "name", None):
            networks.append((service.network.name, "bridge"))

        deployer = DeployFacade(
            name=container_name,
            tag=deploy_item.version,
            zip_filename=deploy_item.zip_file.path if deploy_item.zip_file else "",
            dockerfile_text=dockerfile_text,
            max_cpu=service.plan.max_cpu,
            max_ram=service.plan.max_ram,
            networks=networks,
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
            worker_count=worker_count,
        )
        # Pass optional celery_app through environment so Dockerfile layer can use it
        # if the generator supports it; also keep on facade if attribute exists.
        if celery_app:
            try:
                deployer.celery_app = str(celery_app).strip()
            except Exception:
                pass
            if "CELERY_APP" not in environment:
                environment["CELERY_APP"] = str(celery_app).strip()
                deployer.environment = environment

        result = deployer.deploy_result()
        state_tracker.finish(result)

        if not result.success and result.status != "cancelled":
            raise OrchestratorDeploymentError(
                f"Orchestrator compilation failed: {result.message}"
            )
        return result

    @staticmethod
    def _get_volumes_for_service(service):
        """Return all Volume objects attached to the given service."""
        service_id = str(service.id)
        q_legacy = Q(service=service)
        q_json = Q(service_attachments__has_key=service_id)
        return Volume.objects.filter(q_legacy | q_json).distinct()

    @staticmethod
    def _volume_specs(deploy_item: Deploy) -> list:
        """
        Build VolumeSpec list from volumes attached to the service.

        Bind/mode come from Volume.service_attachments[service_id], falling
        back to Volume.default_bind / default_mode.
        """
        specs = []
        service = deploy_item.service
        service_id = str(service.id)

        for volume in DeployService._get_volumes_for_service(service):
            attachments = getattr(volume, "service_attachments", None) or {}
            if not isinstance(attachments, dict):
                attachments = {}
            attrs = attachments.get(service_id) or {}
            if not isinstance(attrs, dict):
                attrs = {}

            bind = (
                attrs.get("bind")
                or getattr(volume, "default_bind", None)
                or getattr(volume, "bind", None)
            )
            mode = (
                attrs.get("mode")
                or getattr(volume, "default_mode", None)
                or getattr(volume, "mode", None)
                or "rw"
            )

            if not bind:
                logger.warning(
                    "Skipping volume '%s' for service %s: no bind path configured.",
                    getattr(volume, "name", volume.pk),
                    service_id,
                )
                continue

            specs.append(
                VolumeSpec(
                    source=volume.name,
                    target=bind,
                    mode=mode,
                    mount_type="volume",
                    size_mb=getattr(volume, "size_mb", None),
                )
            )
        return specs

