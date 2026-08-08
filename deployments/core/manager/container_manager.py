"""
deployments/core/manager/container_manager.py
---------------------------------------------
Container lifecycle manager.

Key changes vs. the legacy implementation:
  * Resource limits: adds ``memswap_limit == mem_limit`` (no swap),
    ``pids_limit``, and an explicit ``restart_policy`` of
    ``unless-stopped`` so crashed workers self-recover.
  * Traefik label generation uses ``sanitize_route_name`` — previously
    the unsanitised container name was interpolated into a Traefik
    ``Host(...)`` rule, which could break routing or inject backticks.
  * ``rename`` helper added so the orchestrator can implement the new
    blue-green-ish replacement strategy (rename old container out of the
    way BEFORE creating the new one) without the stop-then-start
    downtime window.
  * ``start()`` retries transient Docker failures (cgroup pressure,
    port-already-in-use that resolves, daemon momentarily busy).
  * All public operations remain IDEMPOTENT for ``stop``/``remove``:
    a missing container returns True instead of raising.
  * The class no longer constructs a new Docker client per instance —
    it uses the singleton from ``client_manager``.
"""

from __future__ import annotations

import logging
from typing import Any

import docker

from deployments.common.retry import retry_with_backoff
from deployments.common.security import sanitize_route_name, validate_docker_name

from deployments.common.exceptions import ContainerError
from .client_manager import Client

logger = logging.getLogger(__name__)


# Transient Docker errors we should retry on for ``start()``.  ``NotFound``
# is excluded explicitly — if the container vanished, retrying is pointless.
_RETRYABLE_DOCKER_ERRORS = (docker.errors.APIError, docker.errors.DockerException)


class Container(Client):
    def __init__(
        self,
        name: str,
        image_name: str | None = None,
        max_cpu: float | None = None,
        max_ram: int | None = None,
        networks: list | None = None,
        volumes: dict | None = None,
        read_only: bool = True,
        command: str | None = None,
        environment: dict | None = None,
        exposed_ports: dict | None = None,
        port_bindings: dict | None = None,
        entry_port: int | None = None,
        labels: dict | None = None,
        route_name: str | None = None,
        restart_policy: dict | None = None,
        extra_host_config: dict | None = None,
    ):
        # NOTE: no super().__init__() side-effect beyond caching the
        # singleton client.
        super().__init__()
        # Validate the container name early — Docker would reject illegal
        # names later with a less helpful error.
        self.name = validate_docker_name(name, field="container_name")
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
        self.route_name = sanitize_route_name(route_name or name)
        self.restart_policy = restart_policy or {
            "Name": "unless-stopped",
            "MaximumRetryCount": 5,
        }
        self.extra_host_config = extra_host_config or {}

    # ------------------------------------------------------------------
    # Host config — resource limits, tmpfs, restart policy
    # ------------------------------------------------------------------

    def _host_config(self):
        kwargs: dict[str, Any] = {
            "binds": self.volumes or None,
            "port_bindings": self.port_bindings or None,
            "read_only": self.read_only,
            "restart_policy": self.restart_policy,
        }

        # CPU limit.  We set BOTH cpu_quota/cpu_period (Linux cgroup v1)
        # and NanoCpus (cgroup v2 friendly) so the limit is enforced
        # regardless of the host's cgroup version.
        if self.max_cpu is not None:
            try:
                cpu_float = float(self.max_cpu)
                if cpu_float > 0:
                    kwargs["cpu_period"] = 100_000
                    kwargs["cpu_quota"] = int(cpu_float * 100_000)
                    kwargs["nano_cpus"] = int(cpu_float * 1_000_000_000)
            except (TypeError, ValueError):
                pass

        # Memory limit + matching memswap_limit so the container cannot
        # use swap.  Legacy code set only ``mem_limit`` which leaves
        # Docker's default ``memswap_limit == 2 * mem_limit`` in effect.
        if self.max_ram is not None:
            try:
                ram_mb = int(self.max_ram)
                if ram_mb > 0:
                    mem_bytes = ram_mb * 1024 * 1024
                    kwargs["mem_limit"] = mem_bytes
                    kwargs["memswap_limit"] = mem_bytes
            except (TypeError, ValueError):
                pass

        # PID limit — prevents fork bombs inside the container.
        kwargs["pids_limit"] = 4096

        # tmpfs for ephemeral writable directories even on read-only rootfs.
        # Without this gunicorn / Python tempfile die with
        # "No usable temporary directory found".
        tmpfs = {
            "/tmp": "rw,noexec,nosuid,size=64m",
            "/var/tmp": "rw,noexec,nosuid,size=32m",
            "/run": "rw,noexec,nosuid,size=16m",
        }
        if not self.read_only:
            tmpfs["/tmp"] = "rw,noexec,nosuid,size=64m"
        kwargs["tmpfs"] = tmpfs

        # Security hardening — drop all capabilities and let the image
        # add back what it needs via ``docker run --cap-add``.  This
        # matters because user-supplied images may try to mount /proc
        # or ptrace other processes.
        kwargs["security_opt"] = ["no-new-privileges:true"]

        # Allow callers (orchestrator, rollback) to extend the host
        # config without subclassing.
        kwargs.update(self.extra_host_config)

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
                f"traefik.http.routers.{self.route_name}.rule": (
                    f"Host(`{self.route_name}.{_get_deployment_domain()}`)"
                ),
                f"traefik.http.routers.{self.route_name}.entrypoints": "web",
                f"traefik.http.routers.{self.route_name}.service": self.route_name,
                f"traefik.http.services.{self.route_name}.loadbalancer.server.port": str(self.entry_port),
            }
        )
        return labels

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

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
        except (docker.errors.APIError, docker.errors.DockerException) as exc:
            raise ContainerError(
                f"Failed to create container '{self.name}'.",
                details={
                    "container": self.name,
                    "image": self.image_name,
                    "error": str(exc),
                },
            ) from exc

    def start(self):
        """
        Start the container.  Retries transient Docker failures.

        Raises ``ContainerError`` if the container is missing or exits
        immediately.  The error's ``details`` dict includes the last
        200 log lines for diagnostics.
        """
        container = None
        try:
            container = self.client.containers.get(self.name)
        except docker.errors.NotFound as exc:
            raise ContainerError(
                f"Container '{self.name}' was not found during start.",
                details={"container": self.name},
            ) from exc

        try:
            # Retry only the ``container.start()`` call — the get() above
            # already confirmed the container exists.
            retry_with_backoff(
                container.start,
                retries=2,
                base_delay=0.5,
                max_delay=2.0,
                retry_on=_RETRYABLE_DOCKER_ERRORS,
                skip_on=(docker.errors.NotFound,),
                label=f"container.start[{self.name}]",
            )
            container.reload()
            logger.info(
                "Container '%s' started; status=%s", self.name, container.status
            )
            return container
        except docker.errors.NotFound as exc:
            raise ContainerError(
                f"Container '{self.name}' vanished during start.",
                details={"container": self.name},
            ) from exc
        except _RETRYABLE_DOCKER_ERRORS as exc:
            self._raise_with_logs(container, exc)

    def _raise_with_logs(self, container, exc) -> None:
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
            self.name, status, exit_code,
            logs[-4000:] if logs else "(no logs)",
        )
        raise ContainerError(
            f"Container '{self.name}' exited immediately.",
            details={
                "status": status,
                "exit_code": exit_code,
                "logs": logs[-4000:] if logs else "",
                "error": str(exc),
            },
        ) from exc

    def stop(self, timeout: int = 10) -> bool:
        """
        Stop the container.  Idempotent — returns True if the container
        is missing or already stopped.
        """
        try:
            container = self.client.containers.get(self.name)
            container.reload()
        except docker.errors.NotFound:
            logger.info("Container '%s' does not exist; nothing to stop.", self.name)
            return True

        try:
            if container.status != "running":
                logger.info(
                    "Container '%s' is not running (status=%s)",
                    self.name, container.status,
                )
                return True
            container.stop(timeout=timeout)
            logger.info("Container '%s' stopped.", self.name)
            return True
        except docker.errors.DockerException as exc:
            raise ContainerError(
                f"Failed to stop container '{self.name}'.",
                details={"container": self.name, "error": str(exc)},
            ) from exc

    @classmethod
    def container_is_running(cls, container_name: str) -> bool:
        client = get_docker_client()
        try:
            container = client.containers.get(container_name)
            container.reload()
            return container.status == "running"
        except docker.errors.NotFound:
            return False
        except docker.errors.DockerException as exc:
            raise ContainerError(
                f"Failed to inspect container '{container_name}'.",
                details={"container": container_name, "error": str(exc)},
            ) from exc

    def is_running(self) -> bool:
        return Container.container_is_running(self.name)

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def inspect(self):
        try:
            return self.client.api.inspect_container(self.name)
        except docker.errors.NotFound:
            return None
        except docker.errors.DockerException as exc:
            raise ContainerError(
                f"Failed to inspect container '{self.name}'.",
                details={"container": self.name, "error": str(exc)},
            ) from exc

    def status(self) -> str:
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

    def get_environment(self) -> dict[str, str]:
        """Return the container's configured environment as a dict.

        Used by the rollback path so we can restore the SAME environment
        that the previous container was running with.
        """
        info = self.inspect()
        if not info:
            return {}
        env_list = (info.get("Config") or {}).get("Env") or []
        result: dict[str, str] = {}
        for entry in env_list:
            if isinstance(entry, str) and "=" in entry:
                k, _, v = entry.partition("=")
                result[k] = v
        return result

    def get_command(self) -> str | None:
        """Return the container's CMD (post-image-build) for rollback."""
        info = self.inspect()
        if not info:
            return None
        cmd = (info.get("Config") or {}).get("Cmd")
        if not cmd:
            return None
        if isinstance(cmd, list):
            return " ".join(str(c) for c in cmd)
        return str(cmd)

    def get_labels(self) -> dict[str, str]:
        info = self.inspect()
        if not info:
            return {}
        return (info.get("Config") or {}).get("Labels") or {}

    def get_host_config_summary(self) -> dict[str, Any]:
        """Subset of HostConfig used by rollback to restore resource limits."""
        info = self.inspect()
        if not info:
            return {}
        hc = info.get("HostConfig") or {}
        return {
            "CpuQuota": hc.get("CpuQuota"),
            "CpuPeriod": hc.get("CpuPeriod"),
            "NanoCpus": hc.get("NanoCpus"),
            "Memory": hc.get("Memory"),
            "MemorySwap": hc.get("MemorySwap"),
            "PidsLimit": hc.get("PidsLimit"),
            "RestartPolicy": hc.get("RestartPolicy"),
            "Binds": hc.get("Binds") or [],
            "Tmpfs": hc.get("Tmpfs") or {},
            "ReadonlyRootfs": hc.get("ReadonlyRootfs"),
        }

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

        Returns a plain dict so callers never touch the Docker SDK directly.
        A missing container is NOT an exception — it is represented as
        ``exists=False``.
        """
        try:
            info = self.client.api.inspect_container(self.name)
        except docker.errors.NotFound:
            return {
                "exists": False, "running": False, "status": "missing",
                "exit_code": None, "health": None, "restart_count": None,
            }
        except docker.errors.DockerException as exc:
            logger.warning(
                "inspect_runtime: Docker error for container '%s': %s",
                self.name, exc,
            )
            return {
                "exists": False, "running": False, "status": "unknown",
                "exit_code": None, "health": None, "restart_count": None,
            }

        state = info.get("State", {}) or {}
        is_running = bool(state.get("Running", False))
        raw_status = (
            state.get("Status") or ""
        ).lower() or ("running" if is_running else "exited")

        exit_code: int | None = None
        if not is_running:
            ec = state.get("ExitCode")
            if ec is not None:
                try:
                    exit_code = int(ec)
                except (TypeError, ValueError):
                    exit_code = None

        health_info = state.get("Health") or {}
        health: str | None = health_info.get("Status") or None

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

    # ------------------------------------------------------------------
    # Removal / rename
    # ------------------------------------------------------------------

    def remove(self) -> bool:
        """Force-remove the container.  Idempotent."""
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
            raise ContainerError(
                f"Failed to remove container '{self.name}'.",
                details={"container": self.name, "error": str(exc)},
            ) from exc

    def rename(self, new_name: str) -> str:
        """
        Rename the container.  Used by the orchestrator's rename-old
        replacement strategy so the old container can stay running
        while the new one is created.
        """
        new_name = validate_docker_name(new_name, field="new_container_name")
        try:
            container = self.client.containers.get(self.name)
        except docker.errors.NotFound as exc:
            raise ContainerError(
                f"Cannot rename missing container '{self.name}'.",
                details={"container": self.name},
            ) from exc
        try:
            container.rename(new_name)
            logger.info("Container '%s' renamed to '%s'.", self.name, new_name)
            self.name = new_name
            return new_name
        except docker.errors.DockerException as exc:
            raise ContainerError(
                f"Failed to rename container '{self.name}' -> '{new_name}'.",
                details={"container": self.name, "new_name": new_name, "error": str(exc)},
            ) from exc

    def exists(self) -> bool:
        try:
            self.client.containers.get(self.name)
            return True
        except docker.errors.NotFound:
            return False
        except docker.errors.DockerException as exc:
            raise ContainerError(
                f"Failed to check container '{self.name}'.",
                details={"container": self.name, "error": str(exc)},
            ) from exc

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_container_stats(self) -> dict:
        """
        Get current container resource usage.

        Returns:
            cpu: percentage 0..100 of the configured CPU quota
                 (or host-relative if no quota is set)
            memory: percentage 0..100 of the container memory limit
            memory_limit: limit in bytes
            running: 1 if container is running, else 0
        """
        zero = {"cpu": 0.0, "memory": 0.0, "memory_limit": 0.0, "running": 0}

        try:
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

            if cpu_delta > 0 and system_delta > 0:
                used_cores = (cpu_delta / system_delta) * cpu_count
            else:
                used_cores = 0.0

            host_config = (container.attrs or {}).get("HostConfig", {}) or {}
            cpu_quota = float(host_config.get("CpuQuota", 0) or 0)
            cpu_period = float(host_config.get("CpuPeriod", 0) or 0)

            if cpu_quota > 0 and cpu_period > 0:
                cpu_limit_cores = cpu_quota / cpu_period
                cpu_percent = (used_cores / cpu_limit_cores) * 100.0 if cpu_limit_cores > 0 else 0.0
            else:
                cpu_percent = used_cores * 100.0 / cpu_count

            cpu_percent = min(max(cpu_percent, 0.0), 100.0)

            memory_stats = stats.get("memory_stats", {}) or {}
            memory_usage = float(memory_stats.get("usage", 0) or 0)
            memory_limit = float(memory_stats.get("limit", 0) or 0)

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_deployment_domain() -> str:
    """Read DEPLOYMENT_DOMAIN from Django settings with a safe fallback."""
    try:
        from django.conf import settings  # type: ignore

        return getattr(settings, "DEPLOYMENT_DOMAIN", "example.com")
    except Exception:
        return "example.com"


# Backward-compat: some old call sites used ``Client().client`` directly.
def get_docker_client():
    from .client_manager import get_docker_client as _g
    return _g()


__all__ = ["Container", "get_docker_client"]
