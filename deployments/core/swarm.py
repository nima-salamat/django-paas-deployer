"""Docker Swarm runtime backend for PassDeployer.

Dockerfiles remain build inputs. Runtime execution is driven by a
Compose/Stack-shaped specification applied through the Docker Engine API.
The supported replica states are 0 (stopped) and 1 (running).
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

import docker
import yaml
from django.conf import settings

from deployments.common.exceptions import DeploymentError
from deployments.core.manager.client_manager import get_docker_client


@dataclass(frozen=True)
class SwarmTaskState:
    task_id: str
    desired_state: str
    state: str
    node_id: str | None
    node_name: str | None
    error: str
    message: str


@dataclass(frozen=True)
class SwarmServiceState:
    name: str
    service_id: str | None
    replicas_desired: int
    replicas_running: int
    tasks: tuple[SwarmTaskState, ...]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def swarm_enabled() -> bool:
    return _env_bool("SWARM_ENABLED", True)


def _registry() -> str:
    return str(
        getattr(settings, "SWARM_IMAGE_REGISTRY", "")
        or os.environ.get("SWARM_IMAGE_REGISTRY", "")
    ).strip().rstrip("/")


def _namespace() -> str:
    value = str(
        getattr(settings, "SWARM_IMAGE_NAMESPACE", "")
        or os.environ.get("SWARM_IMAGE_NAMESPACE", "passdeployer")
    ).strip().strip("/")
    return value or "passdeployer"


def _service_image_name(service_name: str, tag: str) -> str:
    registry = _registry()
    if not registry:
        return f"{service_name}:{tag}"
    return f"{registry}/{_namespace()}/{service_name}:{tag}"


def _validate_service_name(name: str) -> str:
    value = str(name or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9_.-]{0,62})", value):
        raise DeploymentError(
            f"Invalid Swarm service name: {name!r}",
            stage="swarm_validation",
            code="SWARM_INVALID_SERVICE_NAME",
            user_message="The generated Docker Swarm service name is invalid.",
        )
    return value


def _validate_replicas(value: Any) -> int:
    try:
        replicas = int(value)
    except (TypeError, ValueError) as exc:
        raise DeploymentError(
            "Swarm replicas must be an integer.",
            stage="swarm_validation",
            code="SWARM_INVALID_REPLICA_COUNT",
        ) from exc
    if replicas not in {0, 1}:
        raise DeploymentError(
            "PassDeployer currently supports only 0 or 1 replica per Swarm service.",
            stage="swarm_validation",
            code="SWARM_REPLICA_COUNT_UNSUPPORTED",
            user_message="This installation currently supports exactly one running replica per service.",
        )
    return replicas


def _env_list(environment: dict[str, Any] | None) -> list[str]:
    return [f"{key}={value}" for key, value in sorted((environment or {}).items())]


def _command(value: Any) -> list[str] | None:
    if value in (None, "", []):
        return None
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return ["/bin/sh", "-lc", str(value)]


def _mount_strings(volume_specs: Iterable[Any]) -> list[str]:
    mounts: list[str] = []
    for volume in volume_specs or ():
        source = str(getattr(volume, "source", "") or "")
        target = str(getattr(volume, "target", "") or "")
        if source and target:
            mode = str(getattr(volume, "mode", "rw") or "rw")
            mounts.append(f"{source}:{target}:{mode}")
    return mounts


def _resource_spec(resource_limits: dict[str, Any] | None) -> dict[str, Any]:
    values = dict(resource_limits or {})
    limits: dict[str, Any] = {}
    if values.get("cpu") not in (None, ""):
        limits["cpus"] = str(values["cpu"])
    if values.get("memory_mb") not in (None, ""):
        limits["memory"] = f"{int(values['memory_mb'])}M"
    return limits


def _placement_constraints(runtime_options: dict[str, Any] | None) -> list[str]:
    raw = dict(runtime_options or {}).get("placement_constraints") or []
    if not isinstance(raw, (list, tuple)):
        raise DeploymentError(
            "placement_constraints must be a list.",
            stage="swarm_validation",
            code="SWARM_INVALID_PLACEMENT",
        )
    pattern = re.compile(
        r"^(?:node\.(?:id|hostname|role|platform\.(?:os|arch))|"
        r"node\.labels\.[A-Za-z0-9_.-]+)\s+(?:==|!=)\s+"
        r"[A-Za-z0-9_.:/@=-]+$"
    )
    result: list[str] = []
    for item in raw:
        value = str(item).strip()
        if value and not pattern.fullmatch(value):
            raise DeploymentError(
                f"Unsupported Swarm placement constraint: {value!r}",
                stage="swarm_validation",
                code="SWARM_INVALID_PLACEMENT",
                user_message="The requested node placement constraint is not allowed.",
            )
        if value:
            result.append(value)
    return result


def _service_labels(config) -> dict[str, str]:
    labels = {
        "managed-by": "django-paas-deployer",
        "passdeployer.service": str(config.labels.get("service.id") or ""),
        "passdeployer.deployment": str(config.labels.get("deployment.id") or ""),
        "passdeployer.process": str(config.labels.get("process.name") or "web"),
    }
    labels.update({str(k): str(v) for k, v in (config.labels or {}).items()})

    endpoints = [
        item for item in (config.endpoints or ())
        if item.enabled and item.exposure == "public"
    ]
    primary = endpoints[0] if endpoints else None
    if primary is not None and primary.protocol in {"http", "https", "ws"}:
        router = re.sub(
            r"[^a-z0-9-]", "-", f"{config.name}-{primary.name}".lower()
        ).strip("-")[:50]
        tick = chr(96)
        host = primary.hostname or config.public_host or ""
        labels["traefik.enable"] = "true"
        labels["traefik.swarm.network"] = "proxy_net"
        labels[f"traefik.http.routers.{router}.rule"] = f"Host({tick}{host}{tick})"
        # Host Nginx terminates public TLS in the current installation.
        # Traefik therefore receives HTTP on its internal web entrypoint.
        labels[f"traefik.http.routers.{router}.entrypoints"] = "web"
        labels[f"traefik.http.routers.{router}.service"] = router
        labels[f"traefik.http.services.{router}.loadbalancer.server.port"] = str(primary.target_port)
        if primary.path:
            labels[f"traefik.http.routers.{router}.rule"] += (
                f" && PathPrefix({tick}{primary.path}{tick})"
            )
    return labels


def compile_compose_service(config, *, image_ref: str, replicas: int = 1) -> dict[str, Any]:
    """Compile DeploymentConfig to a Compose/Stack-shaped service spec."""
    replicas = _validate_replicas(replicas)
    name = _validate_service_name(config.name)
    runtime_options = dict(config.runtime_options or {})

    service = {
        "image": image_ref,
        "command": _command(config.start_command),
        "entrypoint": _command(config.entry_point),
        "working_dir": config.working_directory or "/app",
        "read_only": bool(config.read_only),
        "environment": _env_list(config.environment),
        "networks": [str(network.name) for network in (config.networks or ())],
        "volumes": _mount_strings(config.volumes),
        "deploy": {
            "replicas": replicas,
            "restart_policy": {"condition": "on-failure"},
            "update_config": {
                "parallelism": 1,
                "order": "start-first",
                "failure_action": "rollback",
                "monitor": "15s",
            },
            "rollback_config": {
                "parallelism": 1,
                "order": "stop-first",
                "failure_action": "pause",
                "monitor": "15s",
            },
            "resources": {"limits": _resource_spec(config.resource_limits)},
            "placement": {
                "constraints": _placement_constraints(runtime_options)
            },
            "labels": _service_labels(config),
        },
    }

    ports = []
    for endpoint in config.endpoints or ():
        if (
            endpoint.enabled
            and endpoint.exposure == "public"
            and endpoint.protocol in {"tcp", "udp"}
            and endpoint.published_port is not None
        ):
            ports.append(
                {
                    "target": int(endpoint.target_port),
                    "published": int(endpoint.published_port),
                    "protocol": endpoint.protocol,
                    "mode": "ingress",
                }
            )
    if ports:
        service["ports"] = ports

    return {"version": "3.9", "services": {name: service}}


def compose_yaml(spec: dict[str, Any]) -> str:
    return yaml.safe_dump(spec, sort_keys=False, allow_unicode=False)


class SwarmRuntime:
    """Create/update/remove the real Docker Swarm services."""

    def __init__(self, client=None):
        self.client = client or get_docker_client()

    def assert_active(self) -> dict[str, Any]:
        if not swarm_enabled():
            raise DeploymentError(
                "Docker Swarm runtime is disabled.",
                stage="swarm_validation",
                code="SWARM_DISABLED",
                user_message="Docker Swarm runtime is disabled on this installation.",
            )
        try:
            info = self.client.info()
        except docker.errors.DockerException as exc:
            raise DeploymentError(
                f"Cannot inspect the Docker daemon: {exc}",
                stage="swarm_validation",
                code="DOCKER_UNAVAILABLE",
                recoverable=True,
            ) from exc
        swarm = info.get("Swarm") or {}
        if str(swarm.get("LocalNodeState") or "").lower() != "active":
            raise DeploymentError(
                "The connected Docker daemon is not an active Swarm node.",
                stage="swarm_validation",
                code="SWARM_NOT_ACTIVE",
                user_message="Initialize or join Docker Swarm on the Docker manager used by PassDeployer.",
            )
        if not bool(swarm.get("ControlAvailable")):
            raise DeploymentError(
                "The connected Docker node is not a Swarm manager.",
                stage="swarm_validation",
                code="SWARM_NOT_MANAGER",
                user_message="PassDeployer must connect to a Docker Swarm manager.",
            )
        return swarm

    def ensure_network(self, name: str, *, attachable: bool = True) -> str:
        value = str(name or "").strip()
        if not value:
            raise DeploymentError(
                "Swarm network name is empty.",
                stage="network_creation",
                code="SWARM_NETWORK_INVALID",
            )
        try:
            network = self.client.networks.get(value)
            if str((network.attrs or {}).get("Driver") or "").lower() != "overlay":
                raise DeploymentError(
                    f"Docker network {value!r} is not an overlay network.",
                    stage="network_creation",
                    code="SWARM_NETWORK_DRIVER_MISMATCH",
                    user_message=(
                        f"Network {value!r} already exists as a non-Swarm network. "
                        "Create/recreate it as an attachable overlay network before deploying."
                    ),
                )
            return network.id
        except docker.errors.NotFound:
            network = self.client.networks.create(
                value,
                driver="overlay",
                attachable=bool(attachable),
                labels={"managed-by": "django-paas-deployer"},
                check_duplicate=True,
            )
            return network.id

    def _local_manager_node_id(self) -> str | None:
        try:
            info = self.client.info()
            node_id = str((info.get("Swarm") or {}).get("NodeID") or "")
            if node_id:
                return node_id
            local_name = str(info.get("Name") or "")
            for node in self.client.nodes.list():
                attrs = node.attrs or {}
                if str((attrs.get("Description") or {}).get("Hostname") or "") == local_name:
                    return str(node.id)
        except Exception:
            pass
        return None

    def prepare_image(self, local_image_ref: str, service_name: str, tag: str) -> str:
        nodes = self.client.nodes.list()
        if len(nodes) <= 1:
            return local_image_ref
        registry = _registry()
        if not registry:
            raise DeploymentError(
                "A multi-node Swarm requires SWARM_IMAGE_REGISTRY.",
                stage="image_publish",
                code="SWARM_REGISTRY_REQUIRED",
                user_message=(
                    "Configure SWARM_IMAGE_REGISTRY before deploying to a multi-node Swarm."
                ),
            )
        remote_ref = _service_image_name(service_name, tag)
        repository, remote_tag = remote_ref.rsplit(":", 1)
        try:
            username = str(os.environ.get("SWARM_IMAGE_REGISTRY_USERNAME") or "").strip()
            password = os.environ.get("SWARM_IMAGE_REGISTRY_PASSWORD")
            if username and password:
                self.client.login(
                    username=username,
                    password=password,
                    registry=registry,
                )
            image = self.client.images.get(local_image_ref)
            image.tag(repository, tag=remote_tag)
            response = self.client.images.push(
                repository, tag=remote_tag, decode=True
            )
            if isinstance(response, (str, bytes, bytearray)):
                text = response.decode() if isinstance(response, (bytes, bytearray)) else response
                if "error" in text.lower():
                    raise DeploymentError(
                        text,
                        stage="image_publish",
                        code="SWARM_IMAGE_PUSH_FAILED",
                    )
            for row in response or ():
                if isinstance(row, dict) and row.get("error"):
                    raise DeploymentError(
                        str(row["error"]),
                        stage="image_publish",
                        code="SWARM_IMAGE_PUSH_FAILED",
                    )
            return remote_ref
        except DeploymentError:
            raise
        except docker.errors.DockerException as exc:
            raise DeploymentError(
                f"Unable to publish image {remote_ref}: {exc}",
                stage="image_publish",
                code="SWARM_IMAGE_PUSH_FAILED",
                recoverable=True,
            ) from exc

    def _apply_local_volume_pin(self, config, constraints: list[str]) -> list[str]:
        if not config.volumes or not _env_bool("SWARM_LOCAL_VOLUME_PIN", True):
            return constraints
        if len(self.client.nodes.list()) <= 1:
            return constraints
        node_id = self._local_manager_node_id()
        if node_id and not any(item.startswith("node.id ==") for item in constraints):
            constraints.append(f"node.id == {node_id}")
        return constraints

    def _task_states(self, service) -> tuple[SwarmTaskState, ...]:
        rows = []
        for task in service.tasks() or ():
            status = task.get("Status") or {}
            node_name = None
            node_id = task.get("NodeID")
            if node_id:
                try:
                    node = self.client.nodes.get(node_id)
                    attrs = node.attrs or {}
                    node_name = str((attrs.get("Description") or {}).get("Hostname") or node.name)
                except Exception:
                    pass
            rows.append(
                SwarmTaskState(
                    task_id=str(task.get("ID") or ""),
                    desired_state=str(task.get("DesiredState") or ""),
                    state=str(status.get("State") or ""),
                    node_id=str(node_id) if node_id else None,
                    node_name=node_name,
                    error=str(status.get("Err") or ""),
                    message=str(status.get("Message") or ""),
                )
            )
        return tuple(rows)

    def inspect_service(self, name: str) -> SwarmServiceState | None:
        try:
            service = self.client.services.get(_validate_service_name(name))
        except docker.errors.NotFound:
            return None
        tasks = self._task_states(service)
        mode = ((service.attrs or {}).get("Spec") or {}).get("Mode") or {}
        replicas = int((mode.get("Replicated") or {}).get("Replicas") or 0)
        running = sum(
            1 for task in tasks
            if task.state.lower() == "running"
            and task.desired_state.lower() == "running"
        )
        return SwarmServiceState(
            name=str(service.name),
            service_id=str(service.id),
            replicas_desired=replicas,
            replicas_running=running,
            tasks=tasks,
        )

    def wait_ready(self, name: str, *, timeout: float = 60.0) -> SwarmServiceState:
        deadline = time.monotonic() + float(timeout)
        latest = None
        while time.monotonic() < deadline:
            latest = self.inspect_service(name)
            if latest is None:
                raise DeploymentError(
                    f"Swarm service {name!r} disappeared during deployment.",
                    stage="swarm_startup",
                    code="SWARM_SERVICE_MISSING",
                )
            if latest.replicas_desired == 1 and latest.replicas_running == 1:
                return latest
            failed = [
                task for task in latest.tasks
                if task.state.lower() in {"failed", "rejected"}
                and task.desired_state.lower() == "running"
            ]
            if failed:
                task = failed[0]
                raise DeploymentError(
                    f"Swarm task failed: {task.error or task.message or task.state}",
                    stage="swarm_startup",
                    code="SWARM_TASK_FAILED",
                    details={
                        "task_id": task.task_id,
                        "node_id": task.node_id,
                        "node_name": task.node_name,
                        "error": task.error,
                        "message": task.message,
                    },
                )
            time.sleep(1)
        raise DeploymentError(
            f"Swarm service {name!r} did not reach one running task within {timeout:.0f}s.",
            stage="swarm_startup",
            code="SWARM_START_TIMEOUT",
            recoverable=True,
            details={
                "replicas_desired": latest.replicas_desired if latest else None,
                "replicas_running": latest.replicas_running if latest else None,
                "tasks": [task.__dict__ for task in (latest.tasks if latest else ())],
            },
        )

    def _create_kwargs(self, config, *, image_ref: str, compose_spec: dict[str, Any]):
        from docker.types import EndpointSpec, Mount, Resources, RestartPolicy, RollbackConfig, ServiceMode, UpdateConfig

        name = _validate_service_name(config.name)
        service_doc = compose_spec["services"][name]
        deploy_doc = service_doc["deploy"]

        mounts = [
            Mount(
                target=str(volume.target),
                source=str(volume.source),
                type=str(getattr(volume, "mount_type", "volume") or "volume"),
                read_only=str(getattr(volume, "mode", "rw") or "rw") == "ro",
            )
            for volume in (config.volumes or ())
            if getattr(volume, "source", None) and getattr(volume, "target", None)
        ]

        ports = [
            docker.types.Port(
                target_port=int(raw["target"]),
                published_port=int(raw["published"]),
                protocol=str(raw["protocol"]),
                mode=str(raw["mode"]),
            )
            for raw in (service_doc.get("ports") or ())
        ]
        endpoint_spec = EndpointSpec(ports=ports) if ports else None

        limits = deploy_doc.get("resources", {}).get("limits") or {}
        cpu_limit = int(float(limits["cpus"]) * 1_000_000_000) if limits.get("cpus") else None
        memory_limit = None
        if limits.get("memory"):
            memory_limit = int(str(limits["memory"]).rstrip("Mm")) * 1024 * 1024
        resources = Resources(cpu_limit=cpu_limit, mem_limit=memory_limit)

        restart_doc = deploy_doc.get("restart_policy") or {}
        restart_policy = RestartPolicy(
            condition=restart_doc.get("condition"),
            max_attempts=int(restart_doc.get("max_attempts") or 0),
        )
        update_doc = deploy_doc.get("update_config") or {}
        rollback_doc = deploy_doc.get("rollback_config") or {}
        update_config = UpdateConfig(
            parallelism=1,
            order=update_doc.get("order"),
            failure_action=update_doc.get("failure_action"),
            monitor=15_000_000_000,
        )
        rollback_config = RollbackConfig(
            parallelism=1,
            order=rollback_doc.get("order"),
            failure_action=rollback_doc.get("failure_action"),
            monitor=15_000_000_000,
        )

        constraints = self._apply_local_volume_pin(
            config, _placement_constraints(config.runtime_options)
        )

        labels = dict(deploy_doc.get("labels") or {})
        return {
            "name": name,
            "command": service_doc.get("command"),
            "entrypoint": service_doc.get("entrypoint"),
            "workdir": service_doc.get("working_dir"),
            "read_only": bool(service_doc.get("read_only")),
            "env": service_doc.get("environment") or [],
            "labels": labels,
            "container_labels": labels,
            "mode": ServiceMode(mode="replicated", replicas=1),
            "networks": list(service_doc.get("networks") or []),
            "mounts": mounts,
            "resources": resources,
            "restart_policy": restart_policy,
            "update_config": update_config,
            "rollback_config": rollback_config,
            "endpoint_spec": endpoint_spec,
            "constraints": constraints,
        }

    def apply_processes(self, config, *, image_ref: str) -> dict[str, SwarmServiceState]:
        """Apply the ServiceProcess graph as independent Swarm services."""
        from dataclasses import replace

        process_specs = list((config.runtime_options or {}).get("processes") or [])
        if not process_specs:
            process_specs = [{
                "name": "web",
                "process_type": "web",
                "command": config.start_command,
                "entrypoint": config.entry_point,
                "enabled": True,
                "environment": {},
            }]

        self.assert_active()
        results: dict[str, SwarmServiceState] = {}
        for raw in process_specs:
            if not isinstance(raw, dict) or raw.get("enabled", True) is False:
                continue
            process_name = str(raw.get("name") or "web").strip().lower()
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9_.-]{0,30})", process_name):
                raise DeploymentError(
                    f"Invalid Swarm process name: {process_name!r}",
                    stage="swarm_validation",
                    code="SWARM_INVALID_PROCESS_NAME",
                )
            docker_name = config.name if process_name == "web" else _validate_service_name(f"{config.name}-{process_name}")
            process_environment = dict(config.environment or {})
            process_environment.update({str(k): str(v) for k, v in (raw.get("environment") or {}).items()})
            process_endpoints = [
                endpoint for endpoint in (config.endpoints or ())
                if endpoint.process in (None, "", process_name)
            ] if process_name == "web" else [
                endpoint for endpoint in (config.endpoints or ())
                if endpoint.process == process_name
            ]
            process_config = replace(
                config,
                name=docker_name,
                environment=process_environment,
                start_command=raw.get("command") or (config.start_command if process_name == "web" else None),
                entry_point=raw.get("entrypoint") or (config.entry_point if process_name == "web" else None),
                endpoints=process_endpoints,
                labels={
                    **dict(config.labels or {}),
                    "process.name": process_name,
                    "process.type": str(raw.get("process_type") or "custom"),
                },
            )
            replicas = int(raw.get("replicas") or 1)
            if replicas != 1:
                raise DeploymentError(
                    "Only one running replica is supported for every PassDeployer process.",
                    stage="swarm_validation",
                    code="SWARM_REPLICA_COUNT_UNSUPPORTED",
                )
            results[process_name] = self.apply(process_config, image_ref=image_ref)
        return results

    def cleanup_legacy_containers(self, *, service_id: str) -> int:
        """Remove old container-based runtime resources after Swarm activation."""
        removed = 0
        try:
            containers = self.client.containers.list(
                all=True,
                filters={"label": f"service.id={service_id}"},
            )
        except docker.errors.DockerException:
            return 0
        for container in containers:
            labels = getattr(container, "labels", {}) or {}
            if labels.get("managed-by") not in {"django-paas-deployer", "passdeployer"}:
                continue
            try:
                container.remove(force=True)
                removed += 1
            except docker.errors.DockerException:
                pass
        return removed

    def apply(self, config, *, image_ref: str) -> SwarmServiceState:
        self.assert_active()
        for network in config.networks or ():
            self.ensure_network(network.name, attachable=True)
        if any(
            endpoint.enabled
            and endpoint.exposure == "public"
            and endpoint.protocol in {"http", "https", "ws"}
            for endpoint in config.endpoints or ()
        ):
            self.ensure_network("proxy_net", attachable=True)

        image_ref = self.prepare_image(image_ref, config.name, config.tag)
        spec = compile_compose_service(config, image_ref=image_ref, replicas=1)
        name = _validate_service_name(config.name)
        spec["services"][name]["deploy"]["placement"]["constraints"] = (
            self._apply_local_volume_pin(
                config, _placement_constraints(config.runtime_options)
            )
        )
        kwargs = self._create_kwargs(config, image_ref=image_ref, compose_spec=spec)
        try:
            service = self.client.services.get(name)
            service.reload()
            service.update(
                image=image_ref,
                **{key: value for key, value in kwargs.items() if key != "name"},
            )
        except docker.errors.NotFound:
            try:
                service = self.client.services.create(image_ref, **kwargs)
            except docker.errors.APIError as exc:
                raise DeploymentError(
                    f"Unable to create Swarm service {name!r}: {exc}",
                    stage="swarm_create",
                    code="SWARM_SERVICE_CREATE_FAILED",
                    details={"service": name, "compose": spec},
                    recoverable=True,
                ) from exc
        except docker.errors.APIError as exc:
            raise DeploymentError(
                f"Unable to update Swarm service {name!r}: {exc}",
                stage="swarm_update",
                code="SWARM_SERVICE_UPDATE_FAILED",
                details={"service": name, "compose": spec},
                recoverable=True,
            ) from exc
        return self.wait_ready(name, timeout=getattr(config, "health_timeout", 60) or 60)

    def stop(self, name: str) -> None:
        try:
            self.client.services.get(_validate_service_name(name)).scale(0)
        except docker.errors.NotFound:
            return

    def service_names_for_service(self, service_id: str) -> list[str]:
        names: list[str] = []
        try:
            services = self.client.services.list(
                filters={"label": f"passdeployer.service={service_id}"}
            )
            names = [str(service.name) for service in services]
        except docker.errors.DockerException:
            return []
        return names

    def stop_service_group(self, service_id: str) -> None:
        for name in self.service_names_for_service(service_id):
            self.stop(name)

    def remove_service_group(self, service_id: str) -> None:
        for name in self.service_names_for_service(service_id):
            self.remove(name)

    def remove(self, name: str) -> None:
        try:
            self.client.services.get(_validate_service_name(name)).remove()
        except docker.errors.NotFound:
            return

    def service_logs(self, name: str, *, tail: int | str = 200):
        try:
            return self.client.services.get(_validate_service_name(name)).logs(
                stdout=True, stderr=True, timestamps=True, tail=tail
            )
        except docker.errors.NotFound:
            return b""


def sync_swarm_nodes(*, cluster_name: str | None = None) -> dict[str, Any]:
    """Synchronize Swarm node facts and declarative admin settings."""
    from deploy.models import SwarmCluster, SwarmNode

    name = str(
        cluster_name
        or getattr(settings, "SWARM_CLUSTER_NAME", "")
        or os.environ.get("SWARM_CLUSTER_NAME", "default")
    ).strip() or "default"
    cluster, _ = SwarmCluster.objects.get_or_create(name=name)
    if not cluster.enabled:
        return {"status": "disabled", "cluster": cluster.name}

    runtime = SwarmRuntime()
    try:
        runtime.assert_active()
        docker_nodes = runtime.client.nodes.list()
    except Exception as exc:
        SwarmCluster.objects.filter(pk=cluster.pk).update(
            last_error=str(exc),
            updated_at=__import__("django.utils.timezone", fromlist=["timezone"]).timezone.now(),
        )
        raise

    observed_ids = set()
    now = __import__("django.utils.timezone", fromlist=["timezone"]).timezone.now()
    for node in docker_nodes:
        attrs = node.attrs or {}
        spec = attrs.get("Spec") or {}
        status = attrs.get("Status") or {}
        description = attrs.get("Description") or {}
        manager = attrs.get("ManagerStatus") or {}
        docker_id = str(node.id)
        observed_ids.add(docker_id)
        labels = dict(spec.get("Labels") or {})
        row, _ = SwarmNode.objects.get_or_create(
            docker_id=docker_id,
            defaults={
                "cluster": cluster,
                "hostname": str(description.get("Hostname") or node.name),
                "desired_availability": str(spec.get("Availability") or "active"),
                "desired_labels": labels,
            },
        )
        if row.cluster_id != cluster.pk:
            row.cluster_id = cluster.pk
        desired_availability = row.desired_availability or "active"
        desired_labels = dict(row.desired_labels or {})
        if desired_availability not in {"active", "pause", "drain"}:
            desired_availability = "active"
            row.desired_availability = desired_availability

        current_name = str(spec.get("Name") or description.get("Hostname") or node.name)
        current_role = str(spec.get("Role") or "")
        current_availability = str(spec.get("Availability") or "")
        if (
            current_availability != desired_availability
            or labels != desired_labels
        ):
            try:
                node.update(
                    {
                        "Name": current_name,
                        "Role": current_role,
                        "Availability": desired_availability,
                        "Labels": desired_labels,
                    }
                )
                labels = desired_labels
                current_availability = desired_availability
            except Exception as exc:
                row.last_error = str(exc)

        row.hostname = str(description.get("Hostname") or node.name)
        row.role = current_role
        row.observed_availability = current_availability
        row.observed_state = str(status.get("State") or "")
        row.address = str((manager.get("Addr") or "") or ((status.get("Addr") or "")))
        row.labels = labels
        row.cpus = int((description.get("Resources") or {}).get("NanoCPUs") or 0) // 1_000_000_000
        row.memory_bytes = int((description.get("Resources") or {}).get("MemoryBytes") or 0)
        row.manager_reachable = bool(manager.get("Leader") or manager.get("Addr"))
        row.last_synced_at = now
        row.save(update_fields=[
            "cluster", "hostname", "role", "desired_availability",
            "observed_availability", "observed_state", "address", "labels",
            "cpus", "memory_bytes", "manager_reachable", "last_synced_at",
            "last_error", "updated_at",
        ])

    stale = SwarmNode.objects.filter(cluster=cluster).exclude(docker_id__in=observed_ids)
    stale.update(manager_reachable=False, observed_state="missing", last_synced_at=now, updated_at=now)
    SwarmCluster.objects.filter(pk=cluster.pk).update(
        last_synced_at=now,
        last_error="",
        updated_at=now,
    )
    return {
        "status": "ok",
        "cluster": cluster.name,
        "nodes": len(docker_nodes),
        "reachable": sum(1 for node in docker_nodes if (node.attrs or {}).get("Status", {}).get("State") == "ready"),
    }
