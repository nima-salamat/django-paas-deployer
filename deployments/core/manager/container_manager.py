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
        container = None
        try:
            container = self.client.containers.get(self.name)
            container.start()
            container.reload()
            logger.info(
                "Container '%s' started; status=%s", self.name, container.status
            )
            return container
        except docker.errors.NotFound as exc:
            raise ContainerError(
                f"Container '{self.name}' was not found during start."
            ) from exc
        except docker.errors.DockerException as exc:
            logs = ""
            status = "unknown"
            exit_code = None
            if container is not None:
                try:
                    container.reload()
                    status = container.status
                    exit_code = (container.attrs.get("State") or {}).get("ExitCode")
                    raw = container.logs(tail=200)
                    logs = (
                        raw.decode("utf-8", errors="ignore")
                        if isinstance(raw, bytes)
                        else str(raw)
                    )
                except Exception:
                    logger.debug(
                        "Could not fetch logs after start failure for %s",
                        self.name,
                        exc_info=True,
                    )

            logger.error(
                "Container '%s' failed to stay running. status=%s exit=%s\n%s",
                self.name,
                status,
                exit_code,
                logs[-4000:] if logs else "(no logs)",
            )
            raise ContainerError(
                f"Container '{self.name}' exited immediately.",
                details={
                    "status": status,
                    "exit_code": exit_code,
                    "logs": logs[-4000:] if logs else "",
                },
            ) from exc
            
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

    def inspect_runtime(self) -> dict:
        """
        Single-call Docker inspection for the monitoring loop.

        Returns a plain dict so callers never have to touch the Docker SDK
        directly. A missing container is NOT an exception — it is represented
        as ``exists=False``.

        Keys
        ----
        exists        bool   – container exists in Docker
        running       bool   – container state is "running"
        status        str    – "running" | "exited" | "paused" | "missing" | ...
        exit_code     int|None  – last exit code when not running; None if running
        health        str|None  – "healthy" | "unhealthy" | "starting" | None
        restart_count int|None  – number of automatic restarts recorded by Docker

        Performance
        -----------
        One ``inspect_container`` call is made (same as existing ``inspect()``).
        Container stats (CPU/RAM) are intentionally NOT fetched here — use
        ``get_container_stats()`` for that (on-demand via service_status API).
        """
        try:
            info = self.client.api.inspect_container(self.name)
        except docker.errors.NotFound:
            return {
                "exists": False,
                "running": False,
                "status": "missing",
                "exit_code": None,
                "health": None,
                "restart_count": None,
            }
        except docker.errors.DockerException as exc:
            logger.warning(
                "inspect_runtime: Docker error for container '%s': %s",
                self.name, exc,
            )
            # Treat transient Docker errors as "unknown" rather than crashing
            # the monitor loop for this container.
            return {
                "exists": False,
                "running": False,
                "status": "unknown",
                "exit_code": None,
                "health": None,
                "restart_count": None,
            }

        state = info.get("State", {}) or {}
        is_running = bool(state.get("Running", False))

        # Raw Docker status string ("running", "exited", "paused", etc.)
        raw_status = (state.get("Status") or "").lower() or ("running" if is_running else "exited")

        # Exit code is only meaningful when the container is not running
        exit_code: int | None = None
        if not is_running:
            ec = state.get("ExitCode")
            if ec is not None:
                try:
                    exit_code = int(ec)
                except (TypeError, ValueError):
                    exit_code = None

        # Health check status (present only when a HEALTHCHECK is configured)
        health_info = state.get("Health") or {}
        health: str | None = health_info.get("Status") or None

        # Docker restart policy counter
        restart_raw = info.get("RestartCount")
        restart_count: int | None = None
        if restart_raw is not None:
            try:
                restart_count = int(restart_raw)
            except (TypeError, ValueError):
                restart_count = None

        return {
            "exists": True,
            "running": is_running,
            "status": raw_status,
            "exit_code": exit_code,
            "health": health,
            "restart_count": restart_count,
        }

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

        Returns:
            cpu: percentage 0..100 relative to the container CPU quota
                 (or host-relative if no quota is set)
            memory: percentage 0..100 of the container memory limit
            memory_limit: limit in bytes
            running: 1 if container is running, else 0
        """
        zero = {
            "cpu": 0.0,
            "memory": 0.0,
            "memory_limit": 0.0,
            "running": 0,
        }

        try:
            # self.container is never set in __init__; always resolve by name
            container = getattr(self, "container", None)
            if container is None:
                try:
                    container = self.client.containers.get(self.name)
                except docker.errors.NotFound:
                    return zero
                self.container = container

            container.reload()

            if container.status != "running":
                return zero

            stats = container.stats(stream=False)

            # ---- CPU ----
            cpu_stats = stats.get("cpu_stats", {}) or {}
            precpu_stats = stats.get("precpu_stats", {}) or {}

            cpu_usage = cpu_stats.get("cpu_usage", {}) or {}
            precpu_usage = precpu_stats.get("cpu_usage", {}) or {}

            cpu_delta = float(cpu_usage.get("total_usage", 0) or 0) - float(
                precpu_usage.get("total_usage", 0) or 0
            )
            system_delta = float(cpu_stats.get("system_cpu_usage", 0) or 0) - float(
                precpu_stats.get("system_cpu_usage", 0) or 0
            )

            cpu_count = (
                cpu_stats.get("online_cpus")
                or len(cpu_usage.get("percpu_usage", []) or [])
                or 1
            )
            try:
                cpu_count = max(int(cpu_count), 1)
            except (TypeError, ValueError):
                cpu_count = 1

            # Cores currently used by this container (host-relative)
            if cpu_delta > 0 and system_delta > 0:
                used_cores = (cpu_delta / system_delta) * cpu_count
            else:
                used_cores = 0.0

            # Percent of the configured quota (preferred), else host-relative %
            host_config = (container.attrs or {}).get("HostConfig", {}) or {}
            cpu_quota = float(host_config.get("CpuQuota", 0) or 0)
            cpu_period = float(host_config.get("CpuPeriod", 0) or 0)

            if cpu_quota > 0 and cpu_period > 0:
                cpu_limit_cores = cpu_quota / cpu_period
                if cpu_limit_cores > 0:
                    cpu_percent = (used_cores / cpu_limit_cores) * 100.0
                else:
                    cpu_percent = 0.0
            else:
                # No quota: percent of total host CPUs
                cpu_percent = used_cores * 100.0 / cpu_count

            cpu_percent = min(max(cpu_percent, 0.0), 100.0)

            # ---- MEMORY ----
            memory_stats = stats.get("memory_stats", {}) or {}
            memory_usage = float(memory_stats.get("usage", 0) or 0)
            memory_limit = float(memory_stats.get("limit", 0) or 0)

            # Prefer the explicit mem limit from HostConfig when present
            mem_limit_cfg = host_config.get("Memory") or 0
            try:
                mem_limit_cfg = float(mem_limit_cfg or 0)
            except (TypeError, ValueError):
                mem_limit_cfg = 0.0
            if mem_limit_cfg > 0:
                memory_limit = mem_limit_cfg

            memory_percent = (
                (memory_usage / memory_limit) * 100.0 if memory_limit > 0 else 0.0
            )
            memory_percent = min(max(memory_percent, 0.0), 100.0)

            return {
                "cpu": round(cpu_percent, 2),
                "memory": round(memory_percent, 2),
                "memory_limit": memory_limit,
                "running": 1,
            }

        except docker.errors.NotFound:
            return zero
        except Exception as exc:
            logger.exception("Failed to get container stats for '%s': %s", self.name, exc)
            return zero
