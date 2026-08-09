"""
deployments/core/db_deployer.py
---------------------------------
Deploys database containers (MySQL, PostgreSQL, MariaDB, MongoDB, Redis,
Oracle) from credentials stored in Deploy.config.

Unlike application deployments there is NO zip file or Dockerfile build step.
The deployer:
  1. Validates required credential fields are present.
  2. Pulls the official image via the mirror registry.
  3. Stops and removes any existing container for the same service name.
  4. Creates and starts a new container with credentials injected as runtime
     environment variables (never baked into an image layer).
  5. Waits up to 12 seconds for the container to reach running state.

Re-deploy / rebuild semantics
------------------------------
Calling deploy() on an existing DB service is intentionally destructive to
the container but not to volumes:
  - The old container is removed.
  - A new container starts with new credentials from config.
  - Data on named volumes is preserved as long as the volume is re-attached.
  - Data in ephemeral container storage is lost (this is expected).

Supported platforms and required config keys
--------------------------------------------
  mysql      root_password                (+optional: database, username, password)
  mariadb    root_password                (same env convention as MySQL)
  postgresql password                     (+optional: username, database)
  mongodb    username, password
  redis      (none required)              (+optional: password)
  oracle     password
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import docker
from docker.errors import APIError, NotFound

from core.global_settings.config import MIRROR_DOCKER
from deployments.core.exceptions import DeploymentError
from deployments.core.manager.client_manager import Client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Image map
# ---------------------------------------------------------------------------

_DB_IMAGES: dict[str, str] = {
    "mysql":      "mysql:8.0",
    "mariadb":    "mariadb:11",
    "postgresql": "postgres:16-alpine",
    "mongodb":    "mongo:7",
    "redis":      "redis:7-alpine",
    # Oracle XE community image — not on Docker Hub, mirror prefix not applied
    "oracle":     "gvenzl/oracle-xe:21-slim",
}

# Public set used by other modules to check if a platform is a DB platform
DB_PLATFORMS: frozenset[str] = frozenset(_DB_IMAGES.keys())

_DEFAULT_PORTS: dict[str, int] = {
    "mysql":      3306,
    "mariadb":    3306,
    "postgresql": 5432,
    "mongodb":    27017,
    "redis":      6379,
    "oracle":     1521,
}

# Keys that hold credentials — stripped from public API read responses
SENSITIVE_CONFIG_KEYS: frozenset[str] = frozenset({
    "password",
    "root_password",
    "username",
})

# Keys the user is allowed to update via update_db_config
MUTABLE_DB_CONFIG_KEYS: frozenset[str] = frozenset({
    "root_password",
    "password",
    "username",
    "database",
    "port",
    "env",
})


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DBDeployResult:
    success: bool
    message: str
    container_name: str
    platform: str
    port: int | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Environment variable builders — one per platform
# ---------------------------------------------------------------------------

def _mysql_env(cfg: dict) -> dict[str, str]:
    env: dict[str, str] = {
        "MYSQL_ROOT_PASSWORD": str(cfg.get("root_password") or cfg.get("password") or ""),
    }
    if cfg.get("database"):
        env["MYSQL_DATABASE"] = str(cfg["database"])
    if cfg.get("username"):
        env["MYSQL_USER"] = str(cfg["username"])
        env["MYSQL_PASSWORD"] = str(cfg.get("password") or "")
    return env


def _postgres_env(cfg: dict) -> dict[str, str]:
    env: dict[str, str] = {
        "POSTGRES_PASSWORD": str(cfg.get("password") or ""),
    }
    if cfg.get("username"):
        env["POSTGRES_USER"] = str(cfg["username"])
    if cfg.get("database"):
        env["POSTGRES_DB"] = str(cfg["database"])
    return env


def _mongo_env(cfg: dict) -> dict[str, str]:
    env: dict[str, str] = {
        "MONGO_INITDB_ROOT_USERNAME": str(cfg.get("username") or "root"),
        "MONGO_INITDB_ROOT_PASSWORD": str(cfg.get("password") or ""),
    }
    if cfg.get("database"):
        env["MONGO_INITDB_DATABASE"] = str(cfg["database"])
    return env


def _redis_env(cfg: dict) -> dict[str, str]:
    env: dict[str, str] = {}
    if cfg.get("password"):
        env["REDIS_PASSWORD"] = str(cfg["password"])
    return env


def _oracle_env(cfg: dict) -> dict[str, str]:
    pw = str(cfg.get("password") or "")
    return {"ORACLE_PASSWORD": pw, "ORACLE_PWD": pw}


_ENV_BUILDERS: dict[str, Any] = {
    "mysql":      _mysql_env,
    "mariadb":    _mysql_env,   # same convention as MySQL
    "postgresql": _postgres_env,
    "mongodb":    _mongo_env,
    "redis":      _redis_env,
    "oracle":     _oracle_env,
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "mysql":      ["root_password"],
    "mariadb":    ["root_password"],
    "postgresql": ["password"],
    "mongodb":    ["username", "password"],
    "redis":      [],
    "oracle":     ["password"],
}


def validate_db_config(platform: str, cfg: dict) -> list[str]:
    """
    Return a list of human-readable validation error strings.
    An empty list means the config is valid.

    MySQL/MariaDB accept ``password`` as an alias for ``root_password``
    (``_mysql_env`` already falls back the same way).
    """
    errors: list[str] = []

    required = list(_REQUIRED_FIELDS.get(platform, []))
    if platform in ("mysql", "mariadb"):
        if not str(cfg.get("root_password") or "").strip() and str(cfg.get("password") or "").strip():
            required = [k for k in required if k != "root_password"]

    for key in required:
        val = cfg.get(key)
        if not val or not str(val).strip():
            errors.append(f"'{key}' is required for platform '{platform}'.")

    port = cfg.get("port")
    if port is not None:
        try:
            p = int(port)
            if not (1 <= p <= 65535):
                errors.append(f"port {port} is out of range (1–65535).")
            else:
                # Warn (not error) if port doesn't match the platform default —
                # e.g. user sets port=6379 (Redis) for a MySQL deploy.  This is
                # technically valid (host port can be anything) but almost
                # always a copy-paste mistake.
                default = _DEFAULT_PORTS.get(platform)
                if default and p != default and p in _DEFAULT_PORTS.values():
                    errors.append(
                        f"port {p} is the default port for a different "
                        f"database platform; did you mean port {default} "
                        f"for {platform}?"
                    )
        except (TypeError, ValueError):
            errors.append(f"port '{port}' is not a valid integer.")

    # Reserved database names — MySQL/MariaDB reserve several names for
    # system databases.  Creating a user database with one of these names
    # can cause init failures or silent data corruption.
    if platform in ("mysql", "mariadb"):
        reserved = {"mysql", "sys", "information_schema", "performance_schema"}
        db_name = str(cfg.get("database") or "").strip().lower()
        if db_name in reserved:
            errors.append(
                f"database name '{db_name}' is reserved by {platform} "
                f"as a system database; choose a different name."
            )

    return errors


# ---------------------------------------------------------------------------
# Main deployer
# ---------------------------------------------------------------------------

class DBDeployer:
    """
    Deploy or redeploy a database container from ``Deploy.config`` credentials.

    No zip file is required.  The container image is pulled from the mirror
    registry and credentials are injected as runtime environment variables.

    Example usage::

        result = DBDeployer().deploy(
            container_name="app-abc12345-mydb",
            platform="postgresql",
            cfg={
                "password": "s3cret",
                "username": "appuser",
                "database": "appdb",
                "port": 5432,
                "max_cpu": 1,
                "max_ram": 512,
                "volumes": [{"source": "pgdata", "target": "/var/lib/postgresql/data"}],
                "networks": ["proxy_net"],
            },
            event_sink=sink,
            deployment_id=str(deploy.id),
        )
    """

    def deploy(
        self,
        *,
        container_name: str,
        platform: str,
        cfg: dict,
        event_sink=None,
        deployment_id: str | None = None,
        force_reinit: bool = False,
    ) -> DBDeployResult:
        """
        Deploy a database container.

        Parameters
        ----------
        force_reinit : bool, default False
            If True, wipe every named Docker volume bound to this container
            BEFORE starting it, so the DB reinitialises from scratch.
            Use this when a previous deploy failed mid-initialisation and
            left corrupt data in the volume — symptoms include mysqld
            crashing silently within seconds of startup, or repeated
            container restarts with no clear error.
            WARNING: this DESTROYS all data in the affected volumes.
        """
        from deployments.core.deployment_logger import DeploymentLogger

        log = DeploymentLogger(deployment_id=deployment_id, sink=event_sink)

        # ------------------------------------------------------------------
        # 1. Validate config
        # ------------------------------------------------------------------
        errors = validate_db_config(platform, cfg)
        if errors:
            msg = "DB config validation failed: " + "; ".join(errors)
            log.error("validation", msg, progress=100, details={"errors": errors})
            return DBDeployResult(
                success=False, message=msg, container_name=container_name,
                platform=platform, error=msg, details={"errors": errors},
            )
        log.info("validation", f"Config validated for platform '{platform}'.", progress=5)

        # ------------------------------------------------------------------
        # 2. Resolve full image name
        # ------------------------------------------------------------------
        base_image = _DB_IMAGES.get(platform)
        if not base_image:
            msg = f"Unsupported DB platform: '{platform}'."
            log.error("image_pull", msg, progress=100)
            return DBDeployResult(
                success=False, message=msg, container_name=container_name,
                platform=platform, error=msg,
            )

        # Apply mirror prefix only for plain Docker Hub images
        if base_image.startswith(("ghcr.io", "mcr.", "quay.")):
            full_image = base_image
        else:
            full_image = f"{MIRROR_DOCKER}/{base_image}"

        # ------------------------------------------------------------------
        # 3. Pull image
        # ------------------------------------------------------------------
        log.info("image_pull", f"Pulling image '{full_image}'.", progress=10)
        try:
            client = Client()()
            repo, _, tag = full_image.rpartition(":")
            client.images.pull(repo, tag=tag or "latest")
            log.info("image_pull", f"Image '{full_image}' ready.", progress=25)
        except (APIError, docker.errors.DockerException) as exc:
            msg = f"Failed to pull image '{full_image}': {exc}"
            log.error("image_pull", msg, progress=100, details={"image": full_image})
            return DBDeployResult(
                success=False, message=msg, container_name=container_name,
                platform=platform, error=str(exc),
            )

        # ------------------------------------------------------------------
        # 4. Build runtime environment variables
        # ------------------------------------------------------------------
        environment = _ENV_BUILDERS[platform](cfg)

        # Merge any extra env vars the user supplied under cfg["env"]
        extra_env = cfg.get("env") or {}
        if isinstance(extra_env, dict):
            environment.update({str(k): str(v) for k, v in extra_env.items()})

        # Official Redis image ignores REDIS_PASSWORD env; override CMD instead.
        command = None
        if platform == "redis" and cfg.get("password"):
            command = ["redis-server", "--requirepass", str(cfg["password"])]

        # ------------------------------------------------------------------
        # 5. Port bindings
        # ------------------------------------------------------------------
        default_port = _DEFAULT_PORTS.get(platform)
        host_port = cfg.get("port") or default_port

        exposed_ports: dict = {}
        port_bindings: dict = {}
        if default_port and host_port:
            exposed_ports = {f"{default_port}/tcp": {}}
            port_bindings = {f"{default_port}/tcp": [{"HostPort": str(host_port)}]}

        # ------------------------------------------------------------------
        # 6. Networks
        # ------------------------------------------------------------------
        networks: list[str] = []
        for n in cfg.get("networks") or []:
            name = n if isinstance(n, str) else (n.get("name") if isinstance(n, dict) else "")
            if name:
                networks.append(name)

        # ------------------------------------------------------------------
        # 7. Volume binds
        # ------------------------------------------------------------------
        volume_binds: dict[str, dict] = {}
        for vol in cfg.get("volumes") or []:
            if isinstance(vol, dict):
                src = vol.get("source") or vol.get("name")
                tgt = vol.get("target") or vol.get("bind")
                mode = vol.get("mode", "rw")
                if src and tgt:
                    volume_binds[src] = {"bind": tgt, "mode": mode}
                    # Ensure named Docker volumes exist (skip host bind paths)
                    if not str(src).startswith("/"):
                        try:
                            client.volumes.get(src)
                        except NotFound:
                            try:
                                client.volumes.create(name=src)
                                log.info(
                                    "volume_creation",
                                    f"Created volume '{src}'.",
                                    progress=28,
                                )
                            except (APIError, docker.errors.DockerException) as exc:
                                logger.warning(
                                    "Could not create volume '%s': %s", src, exc
                                )

        # ------------------------------------------------------------------
        # 7b. Optional force-reinit — wipe named volumes so the DB
        # reinitialises from scratch.  Used by the rebuild action when
        # the previous deploy failed mid-init and left corrupt data.
        # Host-bind paths (starting with "/") are NEVER wiped — only
        # named Docker volumes managed by the platform.
        # ------------------------------------------------------------------
        if force_reinit and volume_binds:
            for src in list(volume_binds.keys()):
                if str(src).startswith("/"):
                    continue  # never wipe host bind paths
                try:
                    vol_obj = client.volumes.get(src)
                    vol_obj.remove(force=True)
                    log.info(
                        "volume_creation",
                        f"Wiped volume '{src}' for force-reinit.",
                        progress=29,
                    )
                    # Recreate empty
                    client.volumes.create(name=src)
                    log.info(
                        "volume_creation",
                        f"Recreated empty volume '{src}'.",
                        progress=29,
                    )
                except NotFound:
                    # Already gone — fine.
                    pass
                except (APIError, docker.errors.DockerException) as exc:
                    logger.warning(
                        "force_reinit: could not wipe volume '%s': %s", src, exc
                    )
                    log.info(
                        "volume_creation",
                        f"Warning: could not wipe volume '{src}': {exc}. "
                        f"The DB may fail to start if the volume has "
                        f"corrupt data from a previous failed init.",
                        progress=29,
                    )

        # ------------------------------------------------------------------
        # 8. Remove existing container (safe to call on missing container)
        # ------------------------------------------------------------------
        log.info("container_replacement", "Checking for existing container.", progress=30)
        try:
            old = client.containers.get(container_name)
            old.reload()
            if old.status == "running":
                old.stop(timeout=5)
                log.info("container_replacement", "Stopped existing container.", progress=38)
            old.remove(force=True)
            log.info("container_replacement", "Removed existing container.", progress=50)
        except NotFound:
            log.info("container_replacement", "No existing container found.", progress=50)
        except (APIError, docker.errors.DockerException) as exc:
            msg = f"Failed to remove existing container: {exc}"
            log.error("container_replacement", msg, progress=100)
            return DBDeployResult(
                success=False, message=msg, container_name=container_name,
                platform=platform, error=str(exc),
            )

        # ------------------------------------------------------------------
        # 9. Ensure networks exist
        # ------------------------------------------------------------------
        for net_name in networks:
            try:
                client.networks.get(net_name)
            except NotFound:
                try:
                    client.networks.create(net_name, driver="bridge")
                    log.info("network_creation", f"Created network '{net_name}'.", progress=55)
                except (APIError, docker.errors.DockerException) as exc:
                    logger.warning("Could not create network '%s': %s", net_name, exc)

        networking_config = None
        if networks:
            endpoints = {n: client.api.create_endpoint_config() for n in networks}
            networking_config = client.api.create_networking_config(endpoints)

        # ------------------------------------------------------------------
        # 10. Build host config (resource limits + binds + ports)
        # ------------------------------------------------------------------
        # DB containers need:
        #   * read_only=False (they write data — this is already set below)
        #   * init=True (PID 1 init process via tini) — MySQL/MariaDB/
        #     PostgreSQL entrypoint scripts expect a proper init system.
        #     Without it, MySQL 8.0.36+ fails with "Inappropriate ioctl
        #     for device" when the entrypoint tries to check if mysqld is
        #     running.  This is the root cause of the user's reported bug.
        #   * /var/run/mysqld in tmpfs for MySQL/MariaDB — the official
        #     image declares it as a VOLUME, but on some hosts the
        #     anonymous volume isn't created in time for the entrypoint.
        #   * /var/run/postgresql in tmpfs for PostgreSQL — same reason.
        #   * restart_policy=unless-stopped so the DB auto-recovers after
        #     a host reboot or crash.
        tmpfs: dict[str, str] = {
            "/tmp": "rw,noexec,nosuid,size=64m",
            "/var/tmp": "rw,noexec,nosuid,size=32m",
        }
        if platform in ("mysql", "mariadb"):
            tmpfs["/var/run/mysqld"] = "rw,noexec,nosuid,size=8m"
        elif platform == "postgresql":
            tmpfs["/var/run/postgresql"] = "rw,noexec,nosuid,size=8m"

        hc_kwargs: dict[str, Any] = {
            "binds":         volume_binds or None,
            "port_bindings": port_bindings or None,
            "read_only":     False,   # DB containers must write data
            "tmpfs":          tmpfs,
            "init":          True,    # tini as PID 1 — fixes MySQL ioctl bug
            "restart_policy": {"Name": "unless-stopped"},
        }
        # CPU limit — use nano_cpus exclusively (NOT cpu_quota+cpu_period).
        # Setting cpu_quota without cpu_period, or both nano_cpus AND
        # cpu_period, causes Docker HTTP 400 "Conflicting options".  See
        # container_manager.py for the full rationale.
        max_cpu = cfg.get("max_cpu")
        max_ram = cfg.get("max_ram")
        if max_cpu is not None:
            try:
                cpu_float = float(max_cpu)
                if cpu_float > 0:
                    hc_kwargs["nano_cpus"] = int(cpu_float * 1_000_000_000)
            except (TypeError, ValueError):
                pass
        if max_ram is not None:
            try:
                ram_mb = int(max_ram)
                if ram_mb > 0:
                    mem_bytes = ram_mb * 1024 * 1024
                    hc_kwargs["mem_limit"] = mem_bytes
                    hc_kwargs["memswap_limit"] = mem_bytes  # no swap
            except (TypeError, ValueError):
                pass

        # Progressive fallback chain — same design as container_manager.py.
        # If the engine rejects one option, retry without it.  The final
        # "bare" stage keeps only binds + ports + read_only + init so a DB
        # deploy can NEVER be blocked by a host_config rejection.
        #
        # CRITICAL: ``init=True`` is NEVER stripped.  MySQL 8.0.36+ entrypoint
        # scripts use process-management calls (pgrep/pidof) that fail with
        # "Inappropriate ioctl for device" when the container runs without
        # tini as PID 1.  Stripping init — even as a fallback — reintroduces
        # the bug.  ``init=True`` is supported by every Docker engine since
        # 18.09 (released 2018) so there is no scenario where it should be
        # dropped.  The "bare" safety-net stage also keeps init for the
        # same reason.
        fallbacks = [
            ("full config", lambda kw: kw),
            ("without memswap_limit", lambda kw: {k: v for k, v in kw.items() if k != "memswap_limit"}),
            ("without nano_cpus", lambda kw: {k: v for k, v in kw.items() if k != "nano_cpus"}),
            ("without mem_limit", lambda kw: {k: v for k, v in kw.items() if k != "mem_limit"}),
            ("without tmpfs", lambda kw: {k: v for k, v in kw.items() if k != "tmpfs"}),
            ("without restart_policy", lambda kw: {k: v for k, v in kw.items() if k != "restart_policy"}),
            ("bare (binds+ports+read_only+init only)", lambda kw: {
                k: v for k, v in kw.items()
                if k in ("binds", "port_bindings", "read_only", "init")
            }),
        ]

        host_config = None
        last_hc_error: Exception | None = None
        for stage_desc, mutator in fallbacks:
            attempt_kwargs = mutator(dict(hc_kwargs))
            try:
                host_config = client.api.create_host_config(**attempt_kwargs)
                logger.info(
                    "DB host_config built (stage='%s') for '%s'.",
                    stage_desc, container_name,
                )
                break
            except (TypeError, APIError, docker.errors.DockerException) as exc:
                last_hc_error = exc
                logger.warning(
                    "create_host_config failed in stage '%s' for DB '%s': "
                    "%s. Trying next fallback.",
                    stage_desc, container_name, exc,
                )
                continue

        if host_config is None:
            msg = (
                f"Failed to build host_config for DB container "
                f"'{container_name}' after exhausting all fallbacks. "
                f"Last error: {last_hc_error}"
            )
            log.error("container_creation", msg, progress=100)
            return DBDeployResult(
                success=False, message=msg, container_name=container_name,
                platform=platform, error=str(last_hc_error),
            )

        # ------------------------------------------------------------------
        # 11. Create container
        # ------------------------------------------------------------------
        log.info("container_creation", f"Creating container '{container_name}'.", progress=60)
        try:
            resp = client.api.create_container(
                name=container_name,
                image=full_image,
                environment=environment,
                host_config=host_config,
                networking_config=networking_config,
                ports=list(exposed_ports.keys()) or None,
                command=command,
                labels={
                    "managed-by":    "django-paas-deployer",
                    "platform":      platform,
                    "platform-type": "DB",
                },
            )
            container_id = resp.get("Id") or resp.get("id")
        except (APIError, docker.errors.DockerException) as exc:
            msg = f"Failed to create DB container: {exc}"
            log.error("container_creation", msg, progress=100, details={"image": full_image})
            return DBDeployResult(
                success=False, message=msg, container_name=container_name,
                platform=platform, error=str(exc),
            )

        # ------------------------------------------------------------------
        # 12. Start container
        # ------------------------------------------------------------------
        log.info("container_startup", "Starting container.", progress=80)
        try:
            client.api.start(container_id)
        except (APIError, docker.errors.DockerException) as exc:
            msg = f"Failed to start DB container: {exc}"
            log.error("container_startup", msg, progress=100)
            return DBDeployResult(
                success=False, message=msg, container_name=container_name,
                platform=platform, error=str(exc),
            )

        # ------------------------------------------------------------------
        # 13. Wait for running state (platform-aware timeout)
        # ------------------------------------------------------------------
        _HEALTH_WAIT = {
            "mysql": 30, "mariadb": 30, "postgresql": 20,
            "mongodb": 20, "redis": 10, "oracle": 90,
        }
        wait_secs = _HEALTH_WAIT.get(platform, 20)
        final_status = "unknown"
        for _ in range(wait_secs):
            try:
                c = client.containers.get(container_name)
                c.reload()
                final_status = c.status
                if final_status == "running":
                    break
                if final_status in ("exited", "dead"):
                    break
            except NotFound:
                pass
            time.sleep(1)

        if final_status != "running":
            log_tail = ""
            exit_code = None
            try:
                c = client.containers.get(container_name)
                raw = c.logs(tail=50)
                log_tail = (
                    raw.decode("utf-8", "replace")
                    if isinstance(raw, bytes)
                    else str(raw)
                )
                # Capture the exit code — it often tells you exactly why
                # the DB failed (e.g. MySQL exit code 1 = generic error,
                # 137 = OOM kill, 139 = segfault).
                try:
                    exit_code = c.attrs.get("State", {}).get("ExitCode")
                except Exception:
                    pass
            except Exception:
                pass
            # Include the actual DB container logs in the user-visible
            # message — the previous "did not reach running state" message
            # gave the operator no clue WHY it failed.
            #
            # Recovery hint: if the container is exiting repeatedly with
            # little or no error output (common when the volume has corrupt
            # data from a previous failed init), tell the operator to use
            # the rebuild action with force_reinit=True to wipe the volume.
            has_volumes = bool(volume_binds)
            recovery_hint = ""
            if has_volumes and final_status in ("exited", "dead"):
                recovery_hint = (
                    "\n\n--- Recovery hint ---\n"
                    "This DB container has a data volume and is exiting "
                    "without reaching running state. If the container logs "
                    "above show the entrypoint starting mysqld and then "
                    "silently dying (no error message), the volume likely "
                    "has corrupt data from a previous failed initialisation. "
                    "Trigger a rebuild with force_reinit=True (or manually "
                    "delete the volume and redeploy) to force a fresh "
                    "initialisation."
                )
            msg = (
                f"DB container did not reach running state "
                f"(final status: '{final_status}'"
                f"{f', exit code: {exit_code}' if exit_code is not None else ''}). "
                f"Container logs (last 50 lines):\n{log_tail[-2000:]}"
                f"{recovery_hint}"
            )
            log.error(
                "health_check",
                msg,
                progress=100,
                details={
                    "final_status": final_status,
                    "exit_code": exit_code,
                    "logs": log_tail[-2000:],
                },
            )
            return DBDeployResult(
                success=False, message=msg, container_name=container_name,
                platform=platform, error=msg,
                details={
                    "final_status": final_status,
                    "exit_code": exit_code,
                    "logs": log_tail[-2000:],
                },
            )

        log.info(
            "deployment_completed",
            f"Database '{platform}' is running on port {host_port}.",
            progress=100,
            details={"platform": platform, "image": full_image, "port": host_port},
        )
        return DBDeployResult(
            success=True,
            message=f"Database '{platform}' deployed successfully.",
            container_name=container_name,
            platform=platform,
            port=int(host_port) if host_port else None,
            details={"image": full_image},
        )

    # ------------------------------------------------------------------
    # Utility: remove a DB container (used by rebuild / teardown)
    # ------------------------------------------------------------------

    def remove(self, container_name: str) -> bool:
        """
        Stop and remove a DB container.

        Returns True if the container was found and removed, False if it
        was already gone (idempotent).  Raises DeploymentError on unexpected
        Docker API failures.
        """
        try:
            client = Client()()
            c = client.containers.get(container_name)
            c.reload()
            if c.status == "running":
                c.stop(timeout=5)
            c.remove(force=True)
            logger.info("DB container '%s' removed.", container_name)
            return True
        except NotFound:
            return False
        except (APIError, docker.errors.DockerException) as exc:
            raise DeploymentError(
                f"Failed to remove DB container '{container_name}'.",
                stage="container_removal",
                details={"error": str(exc)},
            ) from exc
