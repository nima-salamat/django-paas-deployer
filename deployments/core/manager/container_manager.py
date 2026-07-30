import logging

import docker

from .client_manager import Client
from deployments.core.exceptions import ContainerError
from django.conf import settings
logger = logging.getLogger(__name__)


class Container(Client):
    def __init__(
        self,
        name: str,
        image_name: str = None,
        max_cpu: float = None,
        max_ram: int = None,
        networks: list = None,
        volumes: dict = None,
        read_only: bool = True,
        command: str = None,
        environment: dict = None,
        exposed_ports: dict = None,
        port_bindings: dict = None,
        entry_port=None,
        labels: dict = None,
        route_name: str = None,
    ):
        super().__init__()
        self.name = name
        self.image_name = image_name
        self.max_cpu = max_cpu
        self.max_ram = max_ram
        self.networks = networks or []
        self.volumes = volumes or {}
        self.read_only = read_only
        self.command = command
        self.environment = environment or {}
        self.exposed_ports = exposed_ports or {}
        self.port_bindings = port_bindings or {}
        self.entry_port = entry_port
        self.labels = labels
        self.route_name = route_name or name

    def _host_config(self):
        kwargs = {
            "binds": self.volumes or None,
            "port_bindings": self.port_bindings or None,
            "read_only": self.read_only,
        }
        if self.max_cpu is not None:
            kwargs["cpu_quota"] = int(float(self.max_cpu) * 100000)
        if self.max_ram is not None:
            kwargs["mem_limit"] = f"{int(self.max_ram)}m"
        return self.client.api.create_host_config(**kwargs)

    def _networking_config(self):
        if not self.networks:
            return None
        endpoints_config = {
            network: self.client.api.create_endpoint_config()
            for network in self.networks
        }
        return self.client.api.create_networking_config(endpoints_config)

    def _labels(self):
        if self.labels is not None:
            return self.labels

        labels = {"managed-by": "django-paas-deployer"}
        if not self.entry_port:
            return labels

        labels.update(
            {
                "traefik.enable": "true",
                "traefik.docker.network": "proxy_net",
                f"traefik.http.routers.{self.route_name}.rule": f"Host(`{self.route_name}.{settings.DEPLOYMENT_DOMAIN}`)",
                f"traefik.http.routers.{self.route_name}.entrypoints": "web",
                f"traefik.http.routers.{self.route_name}.service": self.route_name,
                f"traefik.http.services.{self.route_name}.loadbalancer.server.port": str(self.entry_port),
            }
        )
        return labels

    def create(self):
        try:
            container = self.client.api.create_container(
                name=self.name,
                image=self.image_name,
                command=self.command,
                environment=self.environment,
                host_config=self._host_config(),
                networking_config=self._networking_config(),
                ports=self.exposed_ports or None,
                labels=self._labels(),
            )
            logger.info("Container '%s' created from image '%s'", self.name, self.image_name)
            return container
        except docker.errors.APIError as exc:
            raise ContainerError(
                f"Failed to create container '{self.name}'.",
                details={"container": self.name, "image": self.image_name},
            ) from exc
        except docker.errors.DockerException as exc:
            raise ContainerError(
                f"Failed to create container '{self.name}'.",
                details={"container": self.name, "image": self.image_name},
            ) from exc

    def start(self):
        try:
            container = self.client.containers.get(self.name)
            container.start()
            container.reload()

            
            
            logger.info("Container '%s' started; status=%s", self.name, container.status)
            return container
        except docker.errors.NotFound as exc:
            raise ContainerError(f"Container '{self.name}' was not found during start.") from exc
        except docker.errors.DockerException as exc:
            logs = container.logs(tail=200).decode(errors="ignore")

            print("=" * 80)
            print(logs)
            print("=" * 80)

            raise ContainerError(
                f"Container '{self.name}' exited immediately.",
                details={
                    "status": container.status,
                    "exit_code": container.attrs["State"]["ExitCode"],
                    "logs": logs,
                },
            )
            
    def stop(self, timeout=5):
        try:
            container = self.client.containers.get(self.name)
            container.reload()
        except docker.errors.NotFound:
            logger.info("Container '%s' does not exist; nothing to stop.", self.name)
            return True

        try:
            if container.status != "running":
                logger.info("Container '%s' is not running (status=%s)", self.name, container.status)
                return True
            container.stop(timeout=timeout)
            logger.info("Container '%s' stopped.", self.name)
            return True
        except docker.errors.DockerException as exc:
            raise ContainerError(f"Failed to stop container '{self.name}'.") from exc

    @classmethod
    def container_is_running(cls, container_name: str) -> bool:
        client = Client().client
        try:
            container = client.containers.get(container_name)
            container.reload()
            return container.status == "running"
        except docker.errors.NotFound:
            return False
        except docker.errors.DockerException as exc:
            raise ContainerError(f"Failed to inspect container '{container_name}'.") from exc

    def is_running(self):
        return Container.container_is_running(self.name)

    def inspect(self):
        try:
            return self.client.api.inspect_container(self.name)
        except docker.errors.NotFound:
            return None
        except docker.errors.DockerException as exc:
            raise ContainerError(f"Failed to inspect container '{self.name}'.") from exc

    def status(self):
        info = self.inspect()
        if not info:
            return "missing"
        state = info.get("State", {})
        if state.get("Running"):
            health = state.get("Health", {}).get("Status")
            return health or "running"
        return state.get("Status") or "stopped"

    def get_image_ref(self):
        info = self.inspect()
        if not info:
            return None
        return info.get("Config", {}).get("Image")

    def get_image_identifier(self):
        info = self.inspect()
        if not info:
            return None
        return info.get("Image") or info.get("Config", {}).get("Image")

    def get_exit_code(self):
        info = self.inspect()
        if not info:
            return None
        state = info.get("State", {})
        if state.get("Running"):
            return None
        return state.get("ExitCode")

    def remove(self):
        try:
            container = self.client.containers.get(self.name)
        except docker.errors.NotFound:
            logger.info("Container '%s' not found; nothing to remove.", self.name)
            return True
        try:
            container.remove(force=True)
            logger.info("Container '%s' removed.", self.name)
            return True
        except docker.errors.DockerException as exc:
            raise ContainerError(f"Failed to remove container '{self.name}'.") from exc

    def exists(self) -> bool:
        try:
            self.client.containers.get(self.name)
            return True
        except docker.errors.NotFound:
            return False
        except docker.errors.DockerException as exc:
            raise ContainerError(f"Failed to check container '{self.name}'.") from exc

    def get_container_stats(self) -> dict:
        """
        Get current container resource usage.

        CPU is returned as percentage of the configured CPU quota.
        """

        if not self.container:
            return {
                "cpu": 0.0,
                "memory": 0.0,
                "memory_limit": 0.0,
                "running": 0,
            }

        try:
            self.container.reload()

            if self.container.status != "running":
                return {
                    "cpu": 0.0,
                    "memory": 0.0,
                    "memory_limit": 0.0,
                    "running": 0,
                }

            stats = self.container.stats(stream=False)

            # ============================================================
            # CPU
            # ============================================================
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})

            cpu_usage = cpu_stats.get("cpu_usage", {})
            precpu_usage = precpu_stats.get("cpu_usage", {})

            cpu_delta = (
                cpu_usage.get("total_usage", 0)
                - precpu_usage.get("total_usage", 0)
            )

            system_delta = (
                cpu_stats.get("system_cpu_usage", 0)
                - precpu_stats.get("system_cpu_usage", 0)
            )

            cpu_count = (
                cpu_stats.get("online_cpus")
                or len(cpu_usage.get("percpu_usage", []) or [])
                or 1
            )

            # Docker's normal CPU percentage.
            if cpu_delta > 0 and system_delta > 0:
                docker_cpu_percent = (
                    cpu_delta / system_delta
                ) * cpu_count * 100.0
            else:
                docker_cpu_percent = 0.0

            # ============================================================
            # CPU LIMIT
            # ============================================================
            # CpuQuota/CpuPeriod are in HostConfig, NOT cpu_stats.
            host_config = self.container.attrs.get("HostConfig", {})

            cpu_quota = host_config.get("CpuQuota", 0)
            cpu_period = host_config.get("CpuPeriod", 0)

            if cpu_quota > 0 and cpu_period > 0:
                cpu_limit_cores = cpu_quota / cpu_period

                # Convert Docker's host-relative percentage back to
                # actual CPU cores used, then compare with the quota.
                used_cores = (
                    docker_cpu_percent / 100.0
                ) * cpu_count

                cpu_percent = (
                    used_cores / cpu_limit_cores
                ) * 100.0

                cpu_percent = min(max(cpu_percent, 0.0), 100.0)
            else:
                # No quota configured.
                cpu_percent = max(docker_cpu_percent, 0.0)

            # ============================================================
            # MEMORY
            # ============================================================
            memory_stats = stats.get("memory_stats", {})

            memory_usage = memory_stats.get("usage", 0)
            memory_limit = memory_stats.get("limit", 0)

            memory_percent = (
                (memory_usage / memory_limit) * 100.0
                if memory_limit > 0
                else 0.0
            )

            return {
                "cpu": round(cpu_percent, 2),
                "memory": round(memory_percent, 2),
                "memory_limit": memory_limit,
                "running": 1,
            }

        except Exception as exc:
            logger.exception(
                "Failed to get container stats: %s",
                exc,
            )

            return {
                "cpu": 0.0,
                "memory": 0.0,
                "memory_limit": 0.0,
                "running": 0,
            }