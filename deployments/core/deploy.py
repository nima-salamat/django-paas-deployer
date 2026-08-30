import logging

import docker
from docker.errors import APIError, NotFound

from core.global_settings.config import PlanTypeChoices
from deployments.core.entrypoints import (
    django_find_entrypoint_from_settings,
    django_read_settings_module_from_tar,
)
from deployments.core.exceptions import DeploymentError
from deployments.core.manager.client_manager import Client
from deployments.core.manager.container_manager import Container
from deployments.core.manager.image_manager import Image
from deployments.core.orchestrator import DeploymentOrchestrator
from deployments.core.types import DeploymentConfig, NetworkSpec, VolumeSpec


logger = logging.getLogger(__name__)


def _get_docker_client():
    try:
        return Client()()
    except docker.errors.DockerException:
        logger.exception("Failed to create Docker client from environment.")
        raise


class DeployException(DeploymentError):
    pass


class Deploy:
    """Backward-compatible facade for the deployment orchestrator."""

    def __init__(
        self,
        name,
        tag,
        zip_filename,
        dockerfile_text,
        max_cpu,
        max_ram,
        networks,
        volumes,
        port,
        read_only,
        platform,
        platform_type,
        event_sink=None,
        deployment_id=None,
        # --- new optional parameters (all default to safe values) ----------
        environment=None,
        server_type=None,
        celery=False,
        celery_beat=False,
        entry_point=None,
        worker_count=1,
        resource_limits=None,
        build_options=None,
        build_resource_policy=None,
        runtime_options=None,
        labels=None,
        runtime_version=None,
        package_manager=None,
        working_directory="/app",
        build_dir=None,
        install_command=None,
        build_command=None,
        start_command=None,
        static_dir=None,
        media_dir=None,
    ):
        self.name = name
        self.tag = str(tag)
        self.zip_filename = zip_filename
        self.dockerfile_text = dockerfile_text
        self.max_cpu = max_cpu
        self.max_ram = max_ram
        self.networks = list(networks or [])
        self.volumes = list(volumes or [])
        self.port = port
        self.read_only = read_only
        self.platform = platform
        self.platform_type = platform_type
        self.event_sink = event_sink
        self.deployment_id = deployment_id
        # new
        self.environment = dict(environment) if environment else {}
        self.server_type = server_type or None
        self.celery = bool(celery)
        self.celery_beat = bool(celery_beat) and self.celery
        self.entry_point = (entry_point or "").strip() or None
        try:
            self.worker_count = max(1, int(worker_count or 1))
        except (TypeError, ValueError):
            self.worker_count = 1
        self.resource_limits = dict(resource_limits or {})
        self.build_options = dict(build_options or {})
        self.build_resource_policy = dict(build_resource_policy or {})
        self.runtime_options = dict(runtime_options or {})
        self.labels = {str(k): str(v) for k, v in (labels or {}).items()}
        self.runtime_version = runtime_version
        self.package_manager = package_manager
        self.working_directory = working_directory or "/app"
        self.build_dir = build_dir
        self.install_command = install_command
        self.build_command = build_command
        self.start_command = start_command
        self.static_dir = static_dir
        self.media_dir = media_dir
        self.errors = []
        self.result = None

    def _network_specs(self):
        specs = []
        seen = set()

        for item in self.networks:
            if isinstance(item, NetworkSpec):
                spec = item
            else:
                name, driver = item
                spec = NetworkSpec(name=name, driver=driver or "bridge", internal=True, attachable=True)

            if spec.name not in seen:
                specs.append(spec)
                seen.add(spec.name)

        if str(self.platform_type) == str(PlanTypeChoices.APP) and "proxy_net" not in seen:
            specs.append(NetworkSpec(name="proxy_net", driver="bridge", internal=False, attachable=True))

        return specs

    def _volume_specs(self):
        specs = []
        for item in self.volumes:
            if isinstance(item, VolumeSpec):
                specs.append(item)
                continue

            if isinstance(item, dict):
                specs.append(
                    VolumeSpec(
                        source=item.get("source") or item.get("name"),
                        target=item.get("target") or item.get("bind"),
                        mode=item.get("mode", "rw"),
                        mount_type=item.get("mount_type") or item.get("type", "volume"),
                        driver=item.get("driver", "local"),
                        driver_opts=item.get("driver_opts") or {},
                        create=item.get("create", True),
                        size_mb=item.get("size_mb"),
                    )
                )
                continue

            if isinstance(item, (list, tuple)) and len(item) >= 2:
                specs.append(
                    VolumeSpec(
                        source=item[0],
                        target=item[1],
                        mode=item[2] if len(item) > 2 else "rw",
                        mount_type=item[3] if len(item) > 3 else "volume",
                    )
                )

        return specs

    def _config(self):
        return DeploymentConfig(
            name=self.name,
            tag=self.tag,
            zip_path=self.zip_filename,
            dockerfile_template=self.dockerfile_text,
            max_cpu=self.max_cpu,
            max_ram=self.max_ram,
            networks=self._network_specs(),
            volumes=self._volume_specs(),
            port=self.port,
            read_only=self.read_only,
            platform=self.platform,
            platform_type=self.platform_type,
            runtime_version=getattr(self, "runtime_version", None),
            package_manager=getattr(self, "package_manager", None),
            working_directory=getattr(self, "working_directory", "/app"),
            build_dir=getattr(self, "build_dir", None),
            install_command=getattr(self, "install_command", None),
            build_command=getattr(self, "build_command", None),
            start_command=getattr(self, "start_command", None),
            static_dir=getattr(self, "static_dir", None),
            media_dir=getattr(self, "media_dir", None),
            environment=self.environment,
            server_type=self.server_type,
            celery=self.celery,
            celery_beat=self.celery_beat,
            entry_point=self.entry_point,
            worker_count=self.worker_count,
            resource_limits=self.resource_limits,
            build_options=self.build_options,
            build_resource_policy=self.build_resource_policy,
            runtime_options=self.runtime_options,
            labels=self.labels,
        )

    def deploy(self):
        orchestrator = DeploymentOrchestrator(
            event_sink=self.event_sink,
            deployment_id=self.deployment_id,
            cancel_check=getattr(self, '_cancel_check', None),
        )
        self.result = orchestrator.deploy(self._config())
        self.errors = [] if self.result.success else [DeployException(self.result.message, stage=self.result.stage)]
        return self.errors

    def deploy_result(self):
        orchestrator = DeploymentOrchestrator(
            event_sink=self.event_sink,
            deployment_id=self.deployment_id,
            cancel_check=getattr(self, '_cancel_check', None),
        )
        self.result = orchestrator.deploy(self._config())
        return self.result

    def rollback(self):
        Deploy.remove_all(self.name)

    def connect_proxy_net(self, proxy_network: str = "proxy_net", create_if_missing: bool = False) -> None:
        try:
            client = _get_docker_client()
        except Exception:
            return

        try:
            container = client.containers.get(self.name)
        except NotFound:
            logger.warning("Container '%s' not found locally; skipping network connect.", self.name)
            return
        except APIError as exc:
            logger.exception("Docker API error while getting container '%s': %s", self.name, exc)
            return

        try:
            network = client.networks.get(proxy_network)
        except NotFound:
            if not create_if_missing:
                logger.info("Network '%s' not found, skipping connection.", proxy_network)
                return
            try:
                network = client.networks.create(proxy_network, check_duplicate=True, internal=False)
                logger.info("Created network '%s'.", proxy_network)
            except APIError as exc:
                logger.exception("Failed to create network '%s': %s", proxy_network, exc)
                return
        except APIError as exc:
            logger.exception("Docker API error while getting network '%s': %s", proxy_network, exc)
            return

        try:
            network.connect(container.id)
            logger.info("Connected container '%s' to network '%s'.", self.name, proxy_network)
        except APIError as exc:
            if "already exists" in str(exc) or getattr(exc, "status_code", None) == 409:
                logger.debug("Container '%s' is already connected to '%s'.", self.name, proxy_network)
            else:
                logger.exception("Failed to connect container '%s' to network '%s': %s", self.name, proxy_network, exc)

    def disconnect_proxy_net(self, proxy_network: str = "proxy_net", force: bool = False) -> None:
        try:
            client = _get_docker_client()
        except Exception:
            return

        try:
            network = client.networks.get(proxy_network)
        except NotFound:
            logger.info("Network '%s' not found, skipping disconnect.", proxy_network)
            return
        except APIError as exc:
            logger.exception("Docker API error while getting network '%s': %s", proxy_network, exc)
            return

        try:
            network.disconnect(self.name, force=force)
            logger.info("Container '%s' disconnected from network '%s'.", self.name, proxy_network)
        except NotFound:
            logger.info("Container '%s' was not connected to network '%s'.", self.name, proxy_network)
        except APIError as exc:
            logger.exception("Could not disconnect '%s' from '%s': %s", self.name, proxy_network, exc)

    @classmethod
    def remove_all(cls, name):
        container = Container(name)
        if container.exists():
            container.stop()
            container.remove()

        image = Image(name, tag=None)
        image.remove_all(force=True)

    @classmethod
    def remove_container_only(cls, name):
        """Remove container only, preserving the image for rebuilds."""
        container = Container(name)
        if container.exists():
            container.stop()
            container.remove()

    @classmethod
    def stop_container(cls, name):
        Container(name).stop()

