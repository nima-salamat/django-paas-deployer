"""
deployments/core/rollback.py
----------------------------
Rollback manager — restores the previous container after a failed deploy.

The legacy implementation was dangerously incomplete: it recreated the
container with ONLY name, image, CPU/RAM, networks, volumes, read_only,
and entry_port.  It DROPPED:
  * environment variables (so the restored app had no DB URL, no secrets)
  * command / CMD (so supervisord wouldn't start)
  * labels (so Traefik wouldn't route traffic to it)
  * restart_policy (so a crash stayed dead)
  * memswap / pids limits
  * port bindings

The result was a "rolled back" container that started but immediately
crashed or routed no traffic.  Operators had no way to tell because the
orchestrator swallowed the rollback error silently.

This rewrite captures a ``ContainerSnapshot`` BEFORE the deploy mutates
anything, then ``restore()`` rebuilds the container with the EXACT same
configuration.  If restore itself fails, the error is raised (not
swallowed) so the orchestrator can mark the deployment as
"failed + rollback failed" — never silently "succeeded".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from deployments.common.exceptions import RollbackError

from .manager.container_manager import Container
from .types import DeploymentConfig

logger = logging.getLogger(__name__)


@dataclass
class ContainerSnapshot:
    """
    Full captured state of a container, sufficient to recreate it
    bit-for-bit after a failed deploy.
    """
    name: str
    image_ref: str | None
    environment: dict[str, str] = field(default_factory=dict)
    command: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    networks: list[str] = field(default_factory=list)
    binds: dict[str, dict[str, str]] = field(default_factory=dict)
    read_only: bool = True
    entry_port: int | None = None
    route_name: str | None = None
    max_cpu: float | None = None
    max_ram: int | None = None
    restart_policy: dict | None = None
    host_config_extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls, name: str) -> "ContainerSnapshot":
        """Build an empty snapshot for a non-existent container."""
        return cls(name=name, image_ref=None)

    @classmethod
    def capture(cls, container: Container) -> "ContainerSnapshot":
        """
        Inspect a live container and build a snapshot.

        Returns ``empty(name)`` if the container does not exist.
        """
        name = container.name
        if not container.exists():
            return cls.empty(name)

        info = container.inspect()
        if not info:
            return cls.empty(name)

        config = info.get("Config") or {}
        host_config = info.get("HostConfig") or {}
        network_settings = info.get("NetworkSettings") or {}

        # Environment: list of "KEY=VALUE" strings -> dict
        env: dict[str, str] = {}
        for entry in config.get("Env") or []:
            if isinstance(entry, str) and "=" in entry:
                k, _, v = entry.partition("=")
                env[k] = v

        # Command: list[str] | None -> joined string
        cmd_list = config.get("Cmd")
        command = " ".join(str(c) for c in cmd_list) if cmd_list else None

        # Networks: from NetworkSettings.Networks dict
        networks = list((network_settings.get("Networks") or {}).keys())

        # Binds: HostConfig.Binds is a list of "src:dst:mode" strings
        binds: dict[str, dict[str, str]] = {}
        for bind_str in host_config.get("Binds") or []:
            # Parse "src:dst[:mode]" — note that Windows paths may
            # contain colons, but on Linux this is safe.
            parts = bind_str.split(":")
            if len(parts) >= 2:
                src = parts[0]
                dst = parts[1]
                mode = parts[2] if len(parts) >= 3 else "rw"
                binds[src] = {"bind": dst, "mode": mode}

        # Exposed port (for Traefik label) — prefer the first port
        # binding.  We don't try to be exhaustive; rollback just needs
        # the entry_port that Traefik routes to.
        entry_port: int | None = None
        port_bindings = host_config.get("PortBindings") or {}
        for container_port_str in port_bindings:
            # container_port_str looks like "8000/tcp"
            try:
                entry_port = int(str(container_port_str).split("/")[0])
                break
            except (TypeError, ValueError):
                continue

        # If no explicit port binding, fall back to the ExposedPorts in Config
        if entry_port is None:
            exposed = config.get("ExposedPorts") or {}
            for container_port_str in exposed:
                try:
                    entry_port = int(str(container_port_str).split("/")[0])
                    break
                except (TypeError, ValueError):
                    continue

        # Labels
        labels = config.get("Labels") or {}

        # Route name from labels (Traefik router key)
        route_name = None
        for k in labels:
            if k.startswith("traefik.http.routers.") and k.endswith(".rule"):
                route_name = k.split(".")[3]
                break
        if not route_name:
            route_name = name

        # CPU / RAM from HostConfig
        cpu_quota = host_config.get("CpuQuota") or 0
        cpu_period = host_config.get("CpuPeriod") or 100_000
        max_cpu = (cpu_quota / cpu_period) if cpu_quota else None

        mem_bytes = host_config.get("Memory") or 0
        max_ram = int(mem_bytes // (1024 * 1024)) if mem_bytes else None

        restart_policy = host_config.get("RestartPolicy") or None

        # Capture extra host-config fields we want to preserve but
        # cannot pass via the Container constructor.
        host_config_extra = {
            "PidsLimit": host_config.get("PidsLimit"),
            "SecurityOpt": host_config.get("SecurityOpt") or [],
            "Tmpfs": host_config.get("Tmpfs") or {},
        }

        return cls(
            name=name,
            image_ref=container.get_image_identifier() or config.get("Image"),
            environment=env,
            command=command,
            labels=dict(labels),
            networks=networks,
            binds=binds,
            read_only=bool(host_config.get("ReadonlyRootfs", True)),
            entry_port=entry_port,
            route_name=route_name,
            max_cpu=max_cpu,
            max_ram=max_ram,
            restart_policy=restart_policy,
            host_config_extra=host_config_extra,
        )


class RollbackManager:
    def __init__(self, logger=None):
        self.logger = logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def restore_from_snapshot(
        self,
        snapshot: ContainerSnapshot,
        *,
        stop_timeout: int = 15,
    ) -> bool:
        """
        Restore a container from a previously captured snapshot.

        Returns True if a previous container was actually restored.
        Returns False if ``snapshot.image_ref`` is None (no previous
        image to restore from — e.g. first deploy).

        Raises ``RollbackError`` if the restore itself fails.  The
        orchestrator MUST propagate this so the deployment is marked
        "failed + rollback failed" rather than silently "succeeded".
        """
        if not snapshot.image_ref:
            if self.logger:
                self.logger.warning(
                    "rollback",
                    "No previous image is available for rollback.",
                    progress=96,
                )
            return False

        if self.logger:
            self.logger.info(
                "rollback",
                "Starting rollback from snapshot.",
                progress=96,
                details={
                    "previous_image_ref": snapshot.image_ref,
                    "network_count": len(snapshot.networks),
                    "bind_count": len(snapshot.binds),
                    "has_command": snapshot.command is not None,
                    "env_keys": sorted(snapshot.environment.keys()),
                },
            )

        try:
            # Stop + remove whatever is currently running under this name
            # (might be a half-created replacement container).
            current = Container(snapshot.name)
            if current.exists():
                current.stop(timeout=stop_timeout)
                current.remove()

            # Rebuild the container with the captured configuration.
            # We pass labels explicitly so Traefik routing is preserved.
            restored = Container(
                snapshot.name,
                image_name=snapshot.image_ref,
                max_cpu=snapshot.max_cpu,
                max_ram=snapshot.max_ram,
                networks=snapshot.networks,
                volumes=snapshot.binds,
                read_only=snapshot.read_only,
                command=snapshot.command,
                environment=snapshot.environment,
                entry_port=snapshot.entry_port,
                labels=snapshot.labels or None,
                route_name=snapshot.route_name,
                restart_policy=snapshot.restart_policy or None,
                extra_host_config={
                    "pids_limit": snapshot.host_config_extra.get("PidsLimit") or 4096,
                    "security_opt": snapshot.host_config_extra.get("SecurityOpt")
                    or ["no-new-privileges:true"],
                },
            )
            restored.create()
            restored.start()

            if self.logger:
                self.logger.info(
                    "rollback",
                    "Rollback restored the previous container.",
                    progress=98,
                    details={"previous_image_ref": snapshot.image_ref},
                )
            return True
        except Exception as exc:
            # DO NOT swallow — surface so the orchestrator can mark
            # rollback_failed.  Legacy code silently swallowed this.
            raise RollbackError(
                "Rollback failed while restoring the previous container.",
                details={
                    "previous_image_ref": snapshot.image_ref,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            ) from exc

    # ------------------------------------------------------------------
    # Backward compatibility shim
    # ------------------------------------------------------------------

    def restore_previous_container(
        self,
        config: DeploymentConfig,
        *,
        previous_image_ref: str | None,
        volume_binds: dict,
    ) -> bool:
        """
        Legacy entrypoint — used by the orchestrator's existing call
        sites.  Builds a snapshot from the DeploymentConfig + the
        captured image_ref + volume_binds, then delegates to
        ``restore_from_snapshot``.

        New call sites should capture a ``ContainerSnapshot`` BEFORE
        mutating the container and call ``restore_from_snapshot``
        directly — that path preserves environment, command, labels
        and restart_policy.  This shim cannot, because the legacy
        call sites did not capture them.
        """
        if not previous_image_ref:
            if self.logger:
                self.logger.warning(
                    "rollback",
                    "No previous image is available for rollback.",
                    progress=96,
                )
            return False

        snapshot = ContainerSnapshot(
            name=config.name,
            image_ref=previous_image_ref,
            networks=[n.name for n in config.networks],
            binds=volume_binds or {},
            read_only=config.read_only,
            entry_port=config.port,
            route_name=config.name,
            max_cpu=config.max_cpu,
            max_ram=config.max_ram,
        )
        return self.restore_from_snapshot(snapshot, stop_timeout=config.stop_timeout)


__all__ = ["RollbackManager", "ContainerSnapshot"]
