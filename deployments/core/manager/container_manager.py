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
        resource_limits: dict | None = None,
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
        self.restart_policy = self._normalize_restart_policy(
            restart_policy or {"Name": "unless-stopped"}
        )
        self.extra_host_config = {}
        self.resource_limits = dict(resource_limits or {})

    @staticmethod
    def _normalize_restart_policy(policy: dict | None) -> dict:
        """
        Validate / normalize a Docker restart-policy dict.

        Docker's API only accepts ``MaximumRetryCount`` when the policy
        ``Name`` is ``"on-failure"``.  Any other name (``always``,
        ``unless-stopped``, ``no``) combined with a non-zero
        ``MaximumRetryCount`` is rejected with HTTP 400:

            "invalid restart policy: maximum retry count can only be
             used with 'on-failure'"

        Rather than letting that 400 surface mid-deploy (where it is
        expensive — image already built, networks/volumes already
        created), we strip the offending field here and log a warning.
        """
        if not policy or not isinstance(policy, dict):
            return {"Name": "unless-stopped"}

        name = str(policy.get("Name", "unless-stopped")).strip().lower()
        # Accept hyphenless aliases so callers don't have to remember the
        # exact casing/punctuation Docker expects.
        alias_map = {
            "onfailure": "on-failure",
            "unlessstopped": "unless-stopped",
        }
        name = alias_map.get(name, name)
        valid_names = {"no", "always", "unless-stopped", "on-failure"}
        if name not in valid_names:
            logger.warning(
                "Unknown restart policy Name='%s'; falling back to "
                "'unless-stopped'. Valid names: %s",
                policy.get("Name"), sorted(valid_names),
            )
            name = "unless-stopped"

        normalized: dict[str, Any] = {"Name": name}

        if name == "on-failure":
            max_retries = policy.get("MaximumRetryCount")
            if max_retries is not None:
                try:
                    normalized["MaximumRetryCount"] = int(max_retries)
                except (TypeError, ValueError):
                    logger.warning(
                        "restart_policy MaximumRetryCount=%r is not an "
                        "int; ignoring.", max_retries,
                    )
        elif "MaximumRetryCount" in policy:
            logger.warning(
                "restart_policy Name='%s' cannot carry MaximumRetryCount "
                "(only 'on-failure' can). Stripping it to avoid Docker "
                "HTTP 400 'invalid restart policy'.", name,
            )

        return normalized

    # ------------------------------------------------------------------
    # Host config — resource limits, tmpfs, restart policy
    # ------------------------------------------------------------------

    def _host_config_kwargs(self) -> dict[str, Any]:
        """
        Build the kwargs dict for ``client.api.create_host_config``.

        Returns the dict (not the constructed host_config) so the caller
        can apply progressive fallbacks when a specific Docker engine
        version rejects one of the options.
        """
        kwargs: dict[str, Any] = {
            "binds": self.volumes or None,
            "port_bindings": self.port_bindings or None,
            "read_only": self.read_only,
            "restart_policy": self.restart_policy,
        }

        # CPU limit.  Docker accepts EITHER ``cpu_period`` + ``cpu_quota``
        # (cgroup v1 style) OR ``nano_cpus`` (cgroup v2 style) — setting
        # BOTH causes HTTP 400:
        #     "Conflicting options: Nano CPUs and CPU Period cannot both be set"
        # We use ``nano_cpus`` exclusively because it's the simpler,
        # engine-agnostic API: 1 CPU = 1_000_000_000 nano_cpus.  Docker
        # internally translates it to the right cgroup knobs for the host.
        effective_cpu = self.resource_limits.get("cpu", self.max_cpu)
        if effective_cpu is not None:
            try:
                cpu_float = float(effective_cpu)
                if cpu_float > 0:
                    kwargs["nano_cpus"] = int(cpu_float * 1_000_000_000)
            except (TypeError, ValueError):
                pass

        # Memory limit + matching memswap_limit so the container cannot
        # use swap.  Legacy code set only ``mem_limit`` which leaves
        # Docker's default ``memswap_limit == 2 * mem_limit`` in effect.
        effective_ram = self.resource_limits.get("memory_mb", self.max_ram)
        if effective_ram is not None:
            try:
                ram_mb = int(effective_ram)
                if ram_mb > 0:
                    mem_bytes = ram_mb * 1024 * 1024
                    kwargs["mem_limit"] = mem_bytes
                    swap_mb = self.resource_limits.get("memory_swap_mb")
                    if swap_mb is None:
                        swap_mb = ram_mb
                    kwargs["memswap_limit"] = -1 if int(swap_mb) < 0 else int(swap_mb) * 1024 * 1024
            except (TypeError, ValueError):
                pass

        if self.resource_limits.get("cpu_shares"):
            kwargs["cpu_shares"] = int(self.resource_limits["cpu_shares"])
        if self.resource_limits.get("pids_limit"):
            kwargs["pids_limit"] = int(self.resource_limits["pids_limit"])
        if self.resource_limits.get("cpuset_cpus"):
            kwargs["cpuset_cpus"] = str(self.resource_limits["cpuset_cpus"])
        if self.resource_limits.get("shm_size_mb"):
            kwargs["shm_size"] = int(self.resource_limits["shm_size_mb"]) * 1024 * 1024

        # PID limit — prevents fork bombs inside the container.
        kwargs.setdefault("pids_limit", 4096)

        # tmpfs for ephemeral writable directories even on read-only rootfs.
        # Without this gunicorn / Python tempfile die with
        # "No usable temporary directory found".
        tmpfs = self.resource_limits.get("tmpfs") or {
            "/tmp": "rw,noexec,nosuid,size=64m",
            "/var/tmp": "rw,noexec,nosuid,size=32m",
            "/run": "rw,noexec,nosuid,size=16m",
        }
        kwargs["tmpfs"] = tmpfs

        # Security hardening — no-new-privileges prevents the container
        # process from gaining additional capabilities via setuid binaries.
        # If the engine cannot accept this, the deployment fails closed.
        kwargs["security_opt"] = ["no-new-privileges:true"]

        # Deliberately do not merge arbitrary host config. Values such as
        # privileged, devices, binds, pid_mode, network_mode, cap_add and
        # security_opt are security boundaries and are server-owned.

        return kwargs

    def _host_config(self):
        return self.client.api.create_host_config(**self._host_config_kwargs())

    def _networking_config(self):
        if not self.networks:
            return None
        try:
            endpoints_config = {
                network: self.client.api.create_endpoint_config()
                for network in self.networks
            }
            return self.client.api.create_networking_config(endpoints_config)
        except Exception as exc:
            logger.error(
                "Could not build networking_config for container '%s' "
                "networks=%s: %s. Refusing to fall back to Docker's default "
                "network because that could bypass the private-network policy.",
                self.name, self.networks, exc,
            )
            raise ContainerError(
                f"Failed to configure the required Docker networks for container '{self.name}'.",
                details={"networks": list(self.networks), "error": str(exc)},
            ) from exc

    def _labels(self):
        # Caller-provided labels extend platform labels; they must never
        # suppress the Traefik labels required for public app routing.
        labels = {"managed-by": "django-paas-deployer"}
        if self.labels:
            labels.update({str(k): str(v) for k, v in self.labels.items()})

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

    def _image_exists(self) -> bool:
        """Return True if ``self.image_name`` resolves to a local image."""
        if not self.image_name:
            return False
        try:
            self.client.images.get(self.image_name)
            return True
        except docker.errors.ImageNotFound:
            return False
        except docker.errors.DockerException:
            # Don't crash on transient Docker errors; the create attempt
            # itself will surface a clearer error if the image is missing.
            return True

    def _remove_stale_container_if_present(self) -> bool:
        """
        Remove a stopped container with our name if it exists.

        Returns True if a container was removed, False otherwise.
        Used by create() when the Docker daemon reports a name conflict.
        """
        try:
            existing = self.client.containers.get(self.name)
        except docker.errors.NotFound:
            return False
        except docker.errors.DockerException:
            return False

        try:
            existing.reload()
            status = existing.status
        except Exception:
            status = "unknown"

        # Never remove a running container here — that would cause
        # downtime.  Let the create error surface so an operator can
        # decide what to do.
        if status == "running":
            return False

        try:
            existing.remove(force=True)
            logger.warning(
                "Removed stale stopped container '%s' (status=%s) before "
                "create retry.", self.name, status,
            )
            return True
        except docker.errors.DockerException as exc:
            logger.warning(
                "Could not remove stale container '%s': %s",
                self.name, exc,
            )
            return False

    def create(self):
        """
        Create the container.

        Strategy:
          1. Pre-flight: confirm the image exists locally so we can
             surface a clean error instead of letting Docker return an
             opaque "No such image" 404 mid-create.
          2. Build host_config + networking_config with progressive
             fallback: if a particular option (security_opt, pids_limit,
             tmpfs entry) is rejected by the engine, retry without it
             rather than failing the whole deploy.
          3. On name conflict (409), remove a stale stopped container
             and retry once.

        The actual Docker error is ALWAYS included in the resulting
        ContainerError message — the legacy code swallowed it inside
        ``details``, leaving the operator with only "Failed to create
        container 'X'." and no clue why.
        """
        # Pre-flight image check
        if not self._image_exists():
            raise ContainerError(
                f"Cannot create container '{self.name}': image "
                f"'{self.image_name}' is not present in the local Docker "
                f"image store. Did the build succeed and tag the image?",
                details={
                    "container": self.name,
                    "image": self.image_name,
                    "image_present": False,
                },
            )

        host_kwargs = self._host_config_kwargs()
        networking_config = self._networking_config()
        labels = self._labels()

        # Progressive compatibility fallbacks. Security-critical controls
        # (no-new-privileges and the private network) are intentionally never
        # stripped. If the Docker engine cannot apply them, the deployment
        # fails closed instead of silently running with weaker isolation.
        # Resource constraints are security/billing boundaries, not optional
        # compatibility hints. Never remove CPU/RAM limits as a fallback.
        fallbacks = [
            ("full config", lambda kw: kw),
            ("without tmpfs", lambda kw: {k: v for k, v in kw.items() if k != "tmpfs"}),
            ("without restart_policy", lambda kw: {k: v for k, v in kw.items() if k != "restart_policy"}),
        ]

        last_exc: Exception | None = None
        last_stage_desc = ""

        for attempt in range(2):
            for stage_desc, mutator in fallbacks:
                attempt_kwargs = mutator(dict(host_kwargs))
                try:
                    host_config = self.client.api.create_host_config(**attempt_kwargs)
                except TypeError as te:
                    # An option is unsupported by this docker-py version.
                    logger.warning(
                        "create_host_config rejected kwarg(s) in stage '%s' "
                        "for container '%s': %s. Trying next fallback.",
                        stage_desc, self.name, te,
                    )
                    last_exc = te
                    last_stage_desc = stage_desc
                    continue
                except Exception as he:
                    logger.warning(
                        "create_host_config failed in stage '%s' for "
                        "container '%s': %s. Trying next fallback.",
                        stage_desc, self.name, he,
                    )
                    last_exc = he
                    last_stage_desc = stage_desc
                    continue

                try:
                    container = self.client.api.create_container(
                        name=self.name,
                        image=self.image_name,
                        command=self.command,
                        environment=self.environment,
                        host_config=host_config,
                        networking_config=networking_config,
                        ports=self.exposed_ports or None,
                        labels=labels,
                    )
                    logger.info(
                        "Container '%s' created from image '%s' (stage='%s', "
                        "attempt=%d).",
                        self.name, self.image_name, stage_desc, attempt + 1,
                    )
                    return container
                except docker.errors.APIError as exc:
                    last_exc = exc
                    last_stage_desc = stage_desc
                    status_code = getattr(exc, "status_code", None)
                    msg = str(exc).lower()

                    # 409 Conflict — name already in use.  If the existing
                    # container is stopped, remove it and retry the WHOLE
                    # fallback list once.  If it's running, surface the
                    # error (we never silently destroy a running container).
                    if status_code == 409 or "conflict" in msg or "already in use" in msg:
                        if attempt == 0:
                            removed = self._remove_stale_container_if_present()
                            if removed:
                                logger.info(
                                    "Retrying container create for '%s' after "
                                    "removing stale container.", self.name,
                                )
                                break  # break inner loop; outer loop retries
                        # If we couldn't remove it (running container, or
                        # remove failed) continue to next fallback — it
                        # won't help, but we'll surface a clear error
                        # after exhausting fallbacks.
                        logger.warning(
                            "Container name '%s' already in use and could "
                            "not be removed (attempt=%d, stage='%s').",
                            self.name, attempt + 1, stage_desc,
                        )
                        continue

                    # 404 Not Found — referenced resource (network/volume)
                    # is missing.  No point in trying other fallbacks for
                    # host_config; surface the error immediately.
                    if status_code == 404:
                        raise ContainerError(
                            f"Failed to create container '{self.name}': "
                            f"Docker reported a missing referenced resource. "
                            f"Engine error: {exc}",
                            details={
                                "container": self.name,
                                "image": self.image_name,
                                "stage": stage_desc,
                                "error": str(exc),
                                "status_code": status_code,
                            },
                        ) from exc

                    # Other API errors — try the next fallback
                    logger.warning(
                        "create_container failed in stage '%s' for "
                        "container '%s' (status=%s): %s. Trying next fallback.",
                        stage_desc, self.name, status_code, exc,
                    )
                    continue
                except docker.errors.DockerException as exc:
                    last_exc = exc
                    last_stage_desc = stage_desc
                    logger.warning(
                        "create_container failed in stage '%s' for "
                        "container '%s': %s. Trying next fallback.",
                        stage_desc, self.name, exc,
                    )
                    continue
            else:
                # Inner loop completed without break — no fallback worked.
                break

        # All fallbacks exhausted.  Surface the actual error.
        err_msg = str(last_exc) if last_exc else "unknown error"
        err_type = type(last_exc).__name__ if last_exc else "Unknown"
        status_code = getattr(last_exc, "status_code", None) if last_exc else None

        # CRITICAL: include the actual Docker error in the user-visible
        # message.  The legacy code only put it in details, which were
        # silently dropped by the log formatter.
        message = (
            f"Failed to create container '{self.name}' from image "
            f"'{self.image_name}'. Docker {err_type}: {err_msg}"
        )
        if status_code is not None:
            message += f" (HTTP {status_code})"
        message += (
            f". Last attempted configuration: '{last_stage_desc}'. "
            f"Verified image present locally before create attempt."
        )

        logger.error(
            "Container create exhausted all fallback configurations for "
            "'%s' (image='%s'). Last stage='%s', last error: %s",
            self.name, self.image_name, last_stage_desc, err_msg,
            extra={
                "container": self.name,
                "image": self.image_name,
                "last_stage": last_stage_desc,
                "error_type": err_type,
                "status_code": status_code,
            },
        )

        raise ContainerError(
            message,
            details={
                "container": self.name,
                "image": self.image_name,
                "image_present": True,
                "last_stage": last_stage_desc,
                "error": err_msg,
                "error_type": err_type,
                "status_code": status_code,
                "networks": list(self.networks or []),
                "volumes": list((self.volumes or {}).keys()),
                "host_config_keys": list(host_kwargs.keys()),
            },
        ) from last_exc

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

        # Surface the last few log lines in the user-visible message so
        # the operator can see WHY the container exited (e.g. missing
        # env var, port conflict, import error) without having to dig
        # through ``docker logs``.
        tail = (logs or "").strip().splitlines()[-8:] if logs else []
        tail_text = " | ".join(line.strip() for line in tail if line.strip())
        if tail_text:
            if len(tail_text) > 600:
                tail_text = tail_text[:600] + "..."
            message = (
                f"Container '{self.name}' exited immediately (status={status}, "
                f"exit_code={exit_code}). Last logs: {tail_text}. "
                f"Docker error: {exc}"
            )
        else:
            message = (
                f"Container '{self.name}' exited immediately (status={status}, "
                f"exit_code={exit_code}). No logs available. "
                f"Docker error: {exc}"
            )

        logger.error(
            "Container '%s' failed to stay running. status=%s exit=%s\n%s",
            self.name, status, exit_code,
            logs[-4000:] if logs else "(no logs)",
        )
        raise ContainerError(
            message,
            details={
                "status": status,
                "exit_code": exit_code,
                "logs": logs[-4000:] if logs else "",
                "error": str(exc),
                "error_type": type(exc).__name__,
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
