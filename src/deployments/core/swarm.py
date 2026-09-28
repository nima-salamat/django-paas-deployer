"""Docker Swarm runtime backend for PassDeployer.

Dockerfiles remain build inputs. Runtime execution is driven by a
Compose/Stack-shaped specification applied through the Docker Engine API.
The supported replica states are 0 (stopped) and 1 (running).
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import docker
import yaml
from django.conf import settings
from django.utils import timezone

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
    image: str | None = None


@dataclass(frozen=True)
class SwarmServiceState:
    name: str
    service_id: str | None
    replicas_desired: int
    replicas_running: int
    tasks: tuple[SwarmTaskState, ...]
    labels: Mapping[str, str] = field(default_factory=dict)
    service_image: str | None = None
    update_state: str | None = None
    update_message: str | None = None


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





def _duration_seconds(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    units = (
        ("ms", 0.001),
        ("us", 0.000001),
        ("ns", 0.000000001),
        ("m", 60.0),
        ("h", 3600.0),
        ("s", 1.0),
    )
    for suffix, multiplier in units:
        if text.endswith(suffix):
            return float(text[:-len(suffix)]) * multiplier
    return float(text)


def _healthcheck_spec(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize the process healthcheck to Docker Engine units."""
    raw = dict(raw or {})
    if raw.get("disable"):
        return {"test": ["NONE"]}
    if not raw:
        return None
    test = raw.get("test") or raw.get("cmd") or raw.get("command")
    if not test:
        return None
    interval = _duration_seconds(raw.get("interval", 5), 5.0)
    timeout = _duration_seconds(raw.get("timeout", 3), 3.0)
    start_period = _duration_seconds(raw.get("start_period", raw.get("start-period", 0)), 0.0)
    retries = int(raw.get("retries", 3) or 0)
    if isinstance(test, str):
        test = ["CMD-SHELL", test]
    else:
        test = [str(item) for item in test]
    return {
        "test": test,
        "interval": int(max(0, interval) * 1_000_000_000),
        "timeout": int(max(0, timeout) * 1_000_000_000),
        "retries": max(0, retries),
        "start_period": int(max(0, start_period) * 1_000_000_000),
    }


def _service_labels(config) -> dict[str, str]:
    labels = {
        "managed-by": "django-paas-deployer",
        "passdeployer.service": str(config.labels.get("service.id") or ""),
        "passdeployer.deployment": str(config.labels.get("deployment.id") or ""),
        "passdeployer.process": str(config.labels.get("process.name") or "web"),
    }
    labels.update({str(k): str(v) for k, v in (config.labels or {}).items()})

    for endpoint in (
        item for item in (config.endpoints or ())
        if item.enabled and item.exposure == "public"
        and item.protocol in {"http", "https", "ws"}
    ):
        router = re.sub(
            r"[^a-z0-9-]",
            "-",
            f"{config.name}-{endpoint.name}".lower(),
        ).strip("-")[:50]
        tick = chr(96)
        host = endpoint.hostname or config.public_host or ""
        rule = f"Host({tick}{host}{tick})" if host else ""
        if endpoint.path:
            path_rule = f"PathPrefix({tick}{endpoint.path}{tick})"
            rule = f"{rule} && {path_rule}" if rule else path_rule
        labels["traefik.enable"] = "true"
        labels["traefik.swarm.network"] = "proxy_net"
        if rule:
            labels[f"traefik.http.routers.{router}.rule"] = rule
        labels[f"traefik.http.routers.{router}.entrypoints"] = "web"
        labels[f"traefik.http.routers.{router}.service"] = router
        labels[f"traefik.http.services.{router}.loadbalancer.server.port"] = str(endpoint.target_port)
    return labels


def compile_compose_service(config, *, image_ref: str, replicas: int = 1) -> dict[str, Any]:
    """Compile DeploymentConfig to a Compose/Stack-shaped service spec."""
    replicas = _validate_replicas(replicas)
    name = _validate_service_name(config.name)
    runtime_options = dict(config.runtime_options or {})
    healthcheck = _healthcheck_spec(runtime_options.get("healthcheck"))

    service = {
        "image": image_ref,
        "command": _command(config.start_command),
        "entrypoint": _command(config.entry_point),
        "working_dir": config.working_directory or "/app",
        "read_only": bool(config.read_only),
        "environment": _env_list(config.environment),
        "healthcheck": healthcheck,
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


def _process_resource_limits(
    plan_limits: dict[str, Any] | None,
    process_limits: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge process resources without allowing a process to exceed its Plan."""
    result = dict(plan_limits or {})
    requested = dict(process_limits or {})

    if "cpu" in requested and result.get("cpu") not in (None, ""):
        try:
            value = float(requested["cpu"])
            ceiling = float(result["cpu"])
        except (TypeError, ValueError) as exc:
            raise DeploymentError(
                "Invalid process CPU resource limit.",
                stage="swarm_validation",
                code="SWARM_INVALID_PROCESS_RESOURCE",
            ) from exc
        if value <= 0 or value > ceiling:
            raise DeploymentError(
                f"Process CPU limit {value!r} exceeds the plan ceiling {ceiling!r}.",
                stage="swarm_validation",
                code="SWARM_PROCESS_CPU_LIMIT_EXCEEDED",
                user_message="A process resource limit exceeds the selected plan's CPU limit.",
            )
        result["cpu"] = value

    if "memory_mb" in requested and result.get("memory_mb") not in (None, ""):
        try:
            value = int(requested["memory_mb"])
            ceiling = int(result["memory_mb"])
        except (TypeError, ValueError) as exc:
            raise DeploymentError(
                "Invalid process memory resource limit.",
                stage="swarm_validation",
                code="SWARM_INVALID_PROCESS_RESOURCE",
            ) from exc
        if value <= 0 or value > ceiling:
            raise DeploymentError(
                f"Process memory limit {value!r}MB exceeds the plan ceiling {ceiling!r}MB.",
                stage="swarm_validation",
                code="SWARM_PROCESS_MEMORY_LIMIT_EXCEEDED",
                user_message="A process resource limit exceeds the selected plan's memory limit.",
            )
        result["memory_mb"] = value

    # Only CPU and memory are consumable by the current Swarm compiler.
    return result


class SwarmRuntime:
    """Create/update/remove the real Docker Swarm services."""

    def __init__(self, client=None):
        self.client = client or get_docker_client()
        self._last_apply_operation: dict[str, Any] | None = None
        self._last_apply_recovery: dict[str, Any] = {}

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
        explicit_ids = [
            item for item in constraints if item.startswith("node.id ")
        ]
        local_managed = [
            volume for volume in (config.volumes or ())
            if str(getattr(volume, "mount_type", "volume") or "volume").lower() == "volume"
            and str(getattr(volume, "driver", "local") or "local").lower() == "local"
        ]
        if local_managed and len(self.client.nodes.list()) > 1 and not node_id:
            raise DeploymentError(
                "Cannot determine the Docker node that owns the local volume.",
                stage="swarm_validation",
                code="SWARM_LOCAL_VOLUME_NODE_UNKNOWN",
                user_message=(
                    "PassDeployer cannot safely place this service because the "
                    "node-local volume owner could not be determined."
                ),
                details={
                    "volume_scope": "local",
                    "requested_constraints": explicit_ids,
                },
            )
        if local_managed and explicit_ids:
            expected = f"node.id == {node_id}" if node_id else ""
            if expected and any(item != expected for item in explicit_ids):
                raise DeploymentError(
                    "A local managed volume is provisioned on the Docker manager node, "
                    "but the deployment requests a different Swarm node.",
                    stage="swarm_validation",
                    code="SWARM_LOCAL_VOLUME_NODE_MISMATCH",
                    user_message=(
                        "This service uses node-local persistent storage. "
                        "Its Swarm placement must stay on the volume's node."
                    ),
                    details={
                        "volume_scope": "local",
                        "volume_node_id": node_id,
                        "requested_constraints": explicit_ids,
                    },
                )
        if node_id and not explicit_ids:
            constraints.append(f"node.id == {node_id}")
        return constraints

    def _task_states(self, service) -> tuple[SwarmTaskState, ...]:
        rows = []
        for task in service.tasks() or ():
            status = task.get("Status") or {}
            task_spec = (task.get("Spec") or {}).get("ContainerSpec") or {}
            task_image = str(task_spec.get("Image") or "").strip() or None
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
                    image=task_image,
                )
            )
        return tuple(rows)

    def inspect_service(self, name: str) -> SwarmServiceState | None:
        try:
            service = self.client.services.get(_validate_service_name(name))
        except docker.errors.NotFound:
            return None
        attrs = service.attrs or {}
        spec = attrs.get("Spec") or {}
        task_template = spec.get("TaskTemplate") or {}
        container_spec = task_template.get("ContainerSpec") or {}
        update_status = attrs.get("UpdateStatus") or {}
        mode = spec.get("Mode") or {}
        replicas = int((mode.get("Replicated") or {}).get("Replicas") or 0)
        tasks = self._task_states(service)
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
            labels={
                str(key): str(value)
                for key, value in dict(spec.get("Labels") or {}).items()
            },
            service_image=str(container_spec.get("Image") or "").strip() or None,
            update_state=str(update_status.get("State") or "").strip().lower() or None,
            update_message=str(update_status.get("Message") or "").strip() or None,
        )

    def _service_logs_for_failure(self, name: str, *, tail: int = 200) -> str:
        """Best-effort collection of the failing Swarm service stdout/stderr."""
        try:
            service = self.client.services.get(_validate_service_name(name))
            raw_logs = service.logs(
                stdout=True,
                stderr=True,
                timestamps=True,
                tail=tail,
            )
            if isinstance(raw_logs, bytes):
                return raw_logs.decode("utf-8", errors="replace")
            if not raw_logs:
                return ""
            return "".join(
                chunk.decode("utf-8", errors="replace")
                if isinstance(chunk, bytes)
                else str(chunk)
                for chunk in raw_logs
            )
        except Exception as exc:
            return f"<unable to collect Swarm service logs: {exc}>"

    def wait_ready(
        self,
        name: str,
        *,
        timeout: float = 60.0,
        expected_image: str | None = None,
    ) -> SwarmServiceState:
        """Wait until a Swarm service has a running task for the expected spec."""
        deadline = time.monotonic() + float(timeout)
        latest = None
        rollback_states = {
            "rollback_started",
            "rollback_paused",
            "rollback_completed",
        }
        while time.monotonic() < deadline:
            latest = self.inspect_service(name)
            if latest is None:
                raise DeploymentError(
                    f"Swarm service {name!r} disappeared during deployment.",
                    stage="swarm_startup",
                    code="SWARM_SERVICE_MISSING",
                )

            if expected_image and latest.update_state in rollback_states:
                service_logs = self._service_logs_for_failure(name)
                technical = (
                    f"Swarm service {name!r} rolled back from the requested image. "
                    f"update_state={latest.update_state!r}; "
                    f"update_message={latest.update_message or ''!r}; "
                    f"expected_image={expected_image!r}; "
                    f"service_image={latest.service_image!r}; "
                    f"service_logs={service_logs[-12000:]}"
                )
                raise DeploymentError(
                    technical,
                    stage="swarm_startup",
                    code="SWARM_UPDATE_ROLLED_BACK",
                    user_message="The Swarm service failed to start the new application version and was rolled back.",
                    technical_message=technical,
                    details={
                        "service": name,
                        "update_state": latest.update_state,
                        "update_message": latest.update_message,
                        "expected_image": expected_image,
                        "service_image": latest.service_image,
                        "service_logs": service_logs[-12000:],
                    },
                )

            if (
                expected_image
                and latest.service_image
                and latest.service_image != expected_image
                and latest.update_state not in rollback_states
            ):
                service_logs = self._service_logs_for_failure(name)
                technical = (
                    f"Swarm service {name!r} changed its task image while deployment "
                    f"was waiting for readiness. expected_image={expected_image!r}; "
                    f"service_image={latest.service_image!r}; "
                    f"update_state={latest.update_state!r}; "
                    f"service_logs={service_logs[-12000:]}"
                )
                raise DeploymentError(
                    technical,
                    stage="swarm_startup",
                    code="SWARM_SERVICE_SPEC_CHANGED",
                    user_message="The Swarm service changed while the deployment was starting it.",
                    technical_message=technical,
                    details={
                        "service": name,
                        "expected_image": expected_image,
                        "service_image": latest.service_image,
                        "update_state": latest.update_state,
                        "service_logs": service_logs[-12000:],
                    },
                )

            running = [
                task for task in latest.tasks
                if task.state.lower() == "running"
                and task.desired_state.lower() == "running"
                and (not expected_image or task.image == expected_image)
            ]
            if latest.replicas_desired == 1 and len(running) == 1:
                return latest

            failed = [
                task for task in latest.tasks
                if task.state.lower() in {"failed", "rejected"}
                and task.desired_state.lower() == "running"
            ]
            if failed:
                task = failed[0]
                task_detail = task.error or task.message or task.state
                service_logs = self._service_logs_for_failure(name)
                technical = (
                    f"Swarm task failed: {task_detail}; "
                    f"task_id={task.task_id}; node={task.node_name or task.node_id or ''}; "
                    f"expected_image={expected_image!r}; task_image={task.image!r}; "
                    f"service_image={latest.service_image!r}; "
                    f"update_state={latest.update_state!r}; "
                    f"update_message={latest.update_message or ''!r}; "
                    f"service_logs={service_logs[-12000:]}"
                )
                raise DeploymentError(
                    technical,
                    stage="swarm_startup",
                    code="SWARM_TASK_FAILED",
                    user_message="The Swarm task failed to start. Review deployment diagnostics for the application error.",
                    technical_message=technical,
                    details={
                        "task_id": task.task_id,
                        "node_id": task.node_id,
                        "node_name": task.node_name,
                        "error": task.error,
                        "message": task.message,
                        "task_image": task.image,
                        "expected_image": expected_image,
                        "service_image": latest.service_image,
                        "update_state": latest.update_state,
                        "update_message": latest.update_message,
                        "service_logs": service_logs[-12000:],
                    },
                )
            time.sleep(1)

        raise DeploymentError(
            f"Swarm service {name!r} did not reach the expected running task within {timeout:.0f}s.",
            stage="swarm_startup",
            code="SWARM_START_TIMEOUT",
            recoverable=True,
            details={
                "expected_image": expected_image,
                "service_image": latest.service_image if latest else None,
                "update_state": latest.update_state if latest else None,
                "update_message": latest.update_message if latest else None,
                "replicas_desired": latest.replicas_desired if latest else None,
                "replicas_running": latest.replicas_running if latest else None,
                "tasks": [task.__dict__ for task in (latest.tasks if latest else ())],
            },
        )

    def _create_kwargs(self, config, *, image_ref: str, compose_spec: dict[str, Any]):
        from docker.types import EndpointSpec, Healthcheck, Mount, Resources, RestartPolicy, RollbackConfig, ServiceMode, UpdateConfig

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

        healthcheck_doc = service_doc.get("healthcheck")
        healthcheck = Healthcheck(**healthcheck_doc) if healthcheck_doc else None

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

        # Docker SDK service APIs model the Swarm ContainerSpec using
        # command + args. "entrypoint" is NOT a valid top-level keyword for
        # Service.create() or Service.update().
        #
        # In PassDeployer's DeploymentConfig, entry_point is the effective
        # application start command that replaces the generated Dockerfile CMD
        # (not a separate Docker ENTRYPOINT). compile_compose_service therefore
        # materializes it in the Compose-shaped "entrypoint" field. Prefer that
        # effective command here so it is not accidentally combined with the
        # generated start command a second time.
        swarm_command = (
            service_doc.get("entrypoint")
            if service_doc.get("entrypoint") not in (None, "", [])
            else service_doc.get("command")
        )

        return {
            "name": name,
            "command": swarm_command,
            "workdir": service_doc.get("working_dir"),
            "read_only": bool(service_doc.get("read_only")),
            "healthcheck": healthcheck,
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

        service_id = str((config.labels or {}).get("service.id") or "").strip()
        preexisting_service_names = (
            set(self.service_names_for_service(service_id))
            if service_id
            else set()
        )
        recovery_operations: list[dict[str, Any]] = []
        self._last_apply_operation = None

        def build_recovery() -> dict[str, Any]:
            return {
                "service_id": service_id,
                "preexisting_service_names": sorted(preexisting_service_names),
                "operations": [dict(item) for item in recovery_operations],
                "rollback_services": sorted({
                    str(item["name"])
                    for item in recovery_operations
                    if item.get("preexisting") and item.get("mutation_succeeded")
                }),
                "remove_services": sorted({
                    str(item["name"])
                    for item in recovery_operations
                    if not item.get("preexisting") and item.get("mutation_succeeded")
                }),
            }

        self._last_apply_recovery = build_recovery()
        self.assert_active()
        results: dict[str, SwarmServiceState] = {}
        desired_service_names: set[str] = set()
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
            desired_service_names.add(docker_name)
            process_environment = dict(config.environment or {})
            process_environment.update({str(k): str(v) for k, v in (raw.get("environment") or {}).items()})
            process_resources = _process_resource_limits(
                config.resource_limits,
                raw.get("resources") or {},
            )
            process_metadata = dict(raw.get("metadata") or {})
            process_runtime_options = dict(config.runtime_options or {})
            process_runtime_options["healthcheck"] = dict(raw.get("healthcheck") or {})
            process_runtime_options["placement_constraints"] = list(
                process_metadata.get("placement_constraints")
                or process_runtime_options.get("placement_constraints")
                or []
            )
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
                resource_limits=process_resources,
                runtime_options=process_runtime_options,
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

            try:
                results[process_name] = self.apply(process_config, image_ref=image_ref)
                if self._last_apply_operation:
                    recovery_operations.append(dict(self._last_apply_operation))
                self._last_apply_recovery = build_recovery()
            except Exception as exc:
                if self._last_apply_operation:
                    recovery_operations.append(dict(self._last_apply_operation))
                recovery = build_recovery()
                self._last_apply_recovery = recovery
                if isinstance(exc, DeploymentError):
                    exc.details = {**exc.details, "swarm_recovery": recovery}
                raise

        if not results:
            recovery = build_recovery()
            self._last_apply_recovery = recovery
            raise DeploymentError(
                "No enabled runtime processes were available for the Swarm deployment.",
                stage="swarm_validation",
                code="SWARM_NO_ENABLED_PROCESSES",
                user_message="The deployment has no enabled runtime process to start.",
                details={"swarm_recovery": recovery},
            )

        stale_service_names = sorted(
            set(self.service_names_for_service(service_id)) - desired_service_names
        ) if service_id else []

        # Stale-process deletion is intentionally deferred until after the new
        # revision is activated. Removing an old process before activation would
        # make a later deployment failure unable to restore the previous runtime
        # graph. Cleanup is therefore best-effort and non-fatal after activation.
        recovery = build_recovery()
        recovery["stale_service_names"] = stale_service_names
        self._last_apply_recovery = recovery

        if stale_service_names:
            logger.info(
                "Deferring stale Swarm process cleanup until after activation "
                "for service=%s: %s",
                service_id,
                stale_service_names,
            )

        return results



    def cleanup_stale_process_services(
        self,
        *,
        service_id: str,
        desired_service_names: Iterable[str],
    ) -> tuple[list[str], list[dict[str, str]]]:
        """Best-effort removal of process services no longer in the active graph."""
        service_id = str(service_id or "").strip()
        if not service_id:
            return [], []

        desired = {str(name) for name in desired_service_names}
        existing = set(self.service_names_for_service(service_id))
        stale = sorted(existing - desired)
        removed: list[str] = []
        failures: list[dict[str, str]] = []

        for name in stale:
            try:
                self.remove(name)
                removed.append(name)
            except Exception as exc:
                failures.append({"service": name, "error": str(exc)})

        if removed:
            logger.info(
                "Removed stale active-graph Swarm process services for service=%s: %s",
                service_id,
                removed,
            )
        if failures:
            logger.warning(
                "Some stale Swarm process services could not be removed for service=%s: %s",
                service_id,
                failures,
            )
        return removed, failures

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

    def apply_external_image_service(
        self,
        *,
        name: str,
        image_ref: str,
        environment: dict[str, Any] | None = None,
        command: Any = None,
        networks: Iterable[str] = (),
        volumes: Iterable[dict[str, Any]] = (),
        target_port: int | None = None,
        published_port: int | None = None,
        protocol: str = "tcp",
        resources: dict[str, Any] | None = None,
        labels: dict[str, str] | None = None,
        placement_constraints: Iterable[str] = (),
        healthcheck: dict[str, Any] | None = None,
    ) -> SwarmServiceState:
        """Run a prebuilt external image as a managed Swarm Service."""
        from types import SimpleNamespace

        network_specs = [
            SimpleNamespace(name=str(network), driver="overlay", internal=True, attachable=True)
            for network in networks
            if str(network).strip()
        ]
        volume_specs = [
            SimpleNamespace(
                source=str(item.get("source") or item.get("name") or ""),
                target=str(item.get("target") or item.get("bind") or ""),
                mode=str(item.get("mode") or "rw"),
                mount_type="bind" if str(item.get("source") or item.get("name") or "").startswith("/") else "volume",
            )
            for item in (volumes or ())
            if isinstance(item, dict)
            and (item.get("source") or item.get("name"))
            and (item.get("target") or item.get("bind"))
        ]
        endpoint_specs = []
        if target_port:
            endpoint_specs.append(
                SimpleNamespace(
                    name="database",
                    target_port=int(target_port),
                    published_port=int(published_port) if published_port else None,
                    protocol=str(protocol or "tcp").lower(),
                    exposure="public" if published_port else "internal",
                    hostname="",
                    path="",
                    tls=False,
                    enabled=True,
                    process=None,
                    metadata={},
                )
            )
        config = SimpleNamespace(
            name=_validate_service_name(name),
            tag="external",
            image_ref=image_ref,
            environment={str(k): str(v) for k, v in (environment or {}).items()},
            start_command=command,
            entry_point=None,
            working_directory="/",
            read_only=False,
            resource_limits=dict(resources or {}),
            runtime_options={
                "placement_constraints": [str(item) for item in (placement_constraints or ())],
                "healthcheck": dict(healthcheck or {}),
            },
            networks=network_specs,
            volumes=volume_specs,
            endpoints=endpoint_specs,
            labels={str(k): str(v) for k, v in (labels or {}).items()},
            public_host=None,
            health_timeout=180,
            process=None,
        )
        self.assert_active()
        for network in network_specs:
            self.ensure_network(network.name, attachable=True)
        if endpoint_specs and any(
            endpoint.protocol in {"http", "https", "ws"} and endpoint.exposure == "public"
            for endpoint in endpoint_specs
        ):
            self.ensure_network("proxy_net", attachable=True)

        spec = compile_compose_service(config, image_ref=image_ref, replicas=1)
        service_name = _validate_service_name(name)
        constraints = self._apply_local_volume_pin(
            config,
            _placement_constraints(config.runtime_options),
        )
        spec["services"][service_name]["deploy"]["placement"]["constraints"] = constraints
        kwargs = self._create_kwargs(
            config,
            image_ref=image_ref,
            compose_spec=spec,
        )
        expected_image = None
        try:
            service = self.client.services.get(service_name)
            service.reload()
            service.update(
                image=image_ref,
                **{key: value for key, value in kwargs.items() if key != "name"},
            )
            service.reload()
            observed = self.inspect_service(service_name)
            if observed is not None and observed.update_state in {
                "rollback_started",
                "rollback_paused",
                "rollback_completed",
            }:
                service_logs = self._service_logs_for_failure(service_name)
                technical = (
                    f"Swarm service {service_name!r} was already rolled back before readiness. "
                    f"update_state={observed.update_state!r}; "
                    f"update_message={observed.update_message or ''!r}; "
                    f"service_logs={service_logs[-12000:]}"
                )
                raise DeploymentError(
                    technical,
                    stage="swarm_startup",
                    code="SWARM_UPDATE_ROLLED_BACK",
                    user_message="The Swarm service failed to start the new application version and was rolled back.",
                    technical_message=technical,
                    details={
                        "service": service_name,
                        "update_state": observed.update_state,
                        "update_message": observed.update_message,
                        "expected_image": image_ref,
                        "service_image": observed.service_image,
                        "service_logs": service_logs[-12000:],
                    },
                )
            expected_image = observed.service_image if observed is not None else image_ref
        except docker.errors.NotFound:
            try:
                service = self.client.services.create(image_ref, **kwargs)
                service.reload()
                observed = self.inspect_service(service_name)
                expected_image = observed.service_image if observed is not None else image_ref
            except docker.errors.APIError as exc:
                raise DeploymentError(
                    f"Unable to create Swarm service {service_name!r}: {exc}",
                    stage="swarm_create",
                    code="SWARM_SERVICE_CREATE_FAILED",
                    recoverable=True,
                ) from exc
        except docker.errors.APIError as exc:
            raise DeploymentError(
                f"Unable to update Swarm service {service_name!r}: {exc}",
                stage="swarm_update",
                code="SWARM_SERVICE_UPDATE_FAILED",
                recoverable=True,
            ) from exc
        return self.wait_ready(
            service_name,
            timeout=180,
            expected_image=expected_image,
        )

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
        operation = {
            "name": name,
            "preexisting": False,
            "mutation_started": False,
            "mutation_succeeded": False,
        }
        expected_image = None
        try:
            service = self.client.services.get(name)
            operation["preexisting"] = True
            service.reload()
            operation["mutation_started"] = True
            service.update(
                image=image_ref,
                **{key: value for key, value in kwargs.items() if key != "name"},
            )
            operation["mutation_succeeded"] = True
            service.reload()
            observed = self.inspect_service(name)
            if observed is not None and observed.update_state in {
                "rollback_started",
                "rollback_paused",
                "rollback_completed",
            }:
                service_logs = self._service_logs_for_failure(name)
                technical = (
                    f"Swarm service {name!r} was already rolled back before readiness. "
                    f"update_state={observed.update_state!r}; "
                    f"update_message={observed.update_message or ''!r}; "
                    f"service_logs={service_logs[-12000:]}"
                )
                raise DeploymentError(
                    technical,
                    stage="swarm_startup",
                    code="SWARM_UPDATE_ROLLED_BACK",
                    user_message="The Swarm service failed to start the new application version and was rolled back.",
                    technical_message=technical,
                    details={
                        "service": name,
                        "update_state": observed.update_state,
                        "update_message": observed.update_message,
                        "expected_image": image_ref,
                        "service_image": observed.service_image,
                        "service_logs": service_logs[-12000:],
                    },
                )
            expected_image = observed.service_image if observed is not None else image_ref
        except docker.errors.NotFound:
            operation["mutation_started"] = True
            try:
                service = self.client.services.create(image_ref, **kwargs)
                operation["mutation_succeeded"] = True
                service.reload()
                observed = self.inspect_service(name)
                expected_image = observed.service_image if observed is not None else image_ref
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
        finally:
            self._last_apply_operation = dict(operation)

        return self.wait_ready(
            name,
            timeout=getattr(config, "health_timeout", 60) or 60,
            expected_image=expected_image,
        )

    def rollback_service(self, name: str) -> bool:
        """Request a server-side rollback to the previous Swarm service spec."""
        service = self.client.services.get(_validate_service_name(name))
        service.reload()
        attrs = service.attrs or {}
        update_state = str((attrs.get("UpdateStatus") or {}).get("State") or "").strip().lower()
        if update_state in {"rollback_started", "rollback_paused", "rollback_completed"}:
            return False

        version = int(
            ((attrs.get("Version") or {}).get("Index"))
            or getattr(service, "version", 0)
            or 0
        )
        if version <= 0:
            raise DeploymentError(
                f"Cannot rollback Swarm service {name!r}: missing service version.",
                stage="rollback",
                code="SWARM_ROLLBACK_VERSION_MISSING",
            )

        api = self.client.api
        url = api._url("/services/{0}/update", service.id)
        response = api._post_json(
            url,
            data={},
            params={"version": version, "rollback": "previous"},
        )
        api._result(response, json=True)
        return True

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

    def restart_service_group(self, service_id: str, *, timeout: float = 60.0) -> dict[str, SwarmServiceState]:
        """Restart every managed process service for one application in order."""
        states: dict[str, SwarmServiceState] = {}
        for name in self.service_names_for_service(service_id):
            self.stop(name)
            deadline = time.monotonic() + float(timeout)
            while time.monotonic() < deadline:
                state = self.inspect_service(name)
                if state is None or state.replicas_running == 0:
                    break
                time.sleep(0.5)
            service = self.client.services.get(_validate_service_name(name))
            service.scale(1)
            states[name] = self.wait_ready(name, timeout=timeout)
        return states

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

    def inspect_group(self, service_id: str, *, names: list[str] | None = None) -> dict[str, SwarmServiceState]:
        result: dict[str, SwarmServiceState] = {}
        names = names or self.service_names_for_service(service_id)
        for name in names:
            state = self.inspect_service(name)
            if state is not None:
                result[name] = state
        return result

    def primary_task_container(self, name: str):
        """Return the locally accessible task container, if the task is on this node."""
        service = self.client.services.get(_validate_service_name(name))
        tasks = service.tasks(filters={"desired-state": "running"}) or []
        local_node_id = str(((self.client.info() or {}).get("Swarm") or {}).get("NodeID") or "")
        for task in tasks:
            status = task.get("Status") or {}
            if str(status.get("State") or "").lower() != "running":
                continue
            task_node_id = str(task.get("NodeID") or "")
            container_id = str((status.get("ContainerStatus") or {}).get("ContainerID") or "")
            if not container_id:
                continue
            if task_node_id and local_node_id and task_node_id != local_node_id:
                continue
            try:
                container = self.client.containers.get(container_id)
                container.reload()
                if str(getattr(container, "status", "")).lower() == "running":
                    return container
            except docker.errors.NotFound:
                continue
        return None

    @staticmethod
    def _container_stats_sample(container) -> dict[str, Any]:
        """Read one non-streaming Docker stats sample."""
        try:
            return container.stats(stream=False) or {}
        except TypeError:
            # Some SDK/container test doubles do not accept stream=False.
            return container.stats() or {}

    @staticmethod
    def _cpu_percent(first: dict[str, Any], second: dict[str, Any]) -> float | None:
        first_cpu = (first.get("cpu_stats") or {})
        second_cpu = (second.get("cpu_stats") or {})
        first_total = float((first_cpu.get("cpu_usage") or {}).get("total_usage") or 0)
        second_total = float((second_cpu.get("cpu_usage") or {}).get("total_usage") or 0)
        first_system = float(first_cpu.get("system_cpu_usage") or 0)
        second_system = float(second_cpu.get("system_cpu_usage") or 0)
        cpu_delta = second_total - first_total
        system_delta = second_system - first_system
        if cpu_delta < 0 or system_delta <= 0:
            return None
        online = float(second_cpu.get("online_cpus") or 0)
        if online <= 0:
            online = float(
                len(((second_cpu.get("cpu_usage") or {}).get("percpu_usage") or []))
                or 1
            )
        return round((cpu_delta / system_delta) * online * 100.0, 2)

    @staticmethod
    def _memory_percent(sample: dict[str, Any]) -> float | None:
        memory = sample.get("memory_stats") or {}
        used = float(memory.get("usage") or 0)
        limit = float(memory.get("limit") or 0)
        if used < 0 or limit <= 0:
            return None
        # cgroup v2 can expose cache separately; usage is still the
        # container's accounted memory and is the stable user-facing metric.
        return round((used / limit) * 100.0, 2)

    def service_stats(self, name: str) -> dict[str, Any]:
        state = self.inspect_service(name)
        result: dict[str, Any] = {
            "exists": state is not None,
            "running": bool(state and state.replicas_running == 1),
            "replicas_desired": state.replicas_desired if state else 0,
            "replicas_running": state.replicas_running if state else 0,
            "tasks": [task.__dict__ for task in (state.tasks if state else ())],
            "cpu": None,
            "memory": None,
            "metrics_available": False,
            "metrics_reason": None,
        }
        if state is None:
            result["metrics_reason"] = "service_not_found"
            return result

        container = None
        try:
            container = self.primary_task_container(name)
        except Exception as exc:
            result["metrics_reason"] = f"container_lookup_failed: {exc}"
        if container is None:
            if not result["metrics_reason"]:
                result["metrics_reason"] = "task_container_not_available_on_this_docker_node"
            return result

        try:
            # One sample often has zero CPU delta. Two samples make CPU
            # measurement deterministic for short-lived API requests.
            first = self._container_stats_sample(container)
            time.sleep(0.25)
            second = self._container_stats_sample(container)
            result["cpu"] = self._cpu_percent(first, second)
            result["memory"] = self._memory_percent(second)
            result["metrics_available"] = (
                result["cpu"] is not None or result["memory"] is not None
            )
            if not result["metrics_available"]:
                result["metrics_reason"] = "docker_stats_returned_no_usable_counters"
        except Exception as exc:
            result["metrics_reason"] = f"docker_stats_failed: {exc}"
        return result

    def service_logs(self, name: str, *, tail: int | str = 200):
        try:
            raw = self.client.services.get(_validate_service_name(name)).logs(
                stdout=True, stderr=True, timestamps=True, tail=tail
            )
        except docker.errors.NotFound:
            return b""

        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)

        chunks: list[bytes] = []
        try:
            for chunk in raw:
                if isinstance(chunk, (bytes, bytearray)):
                    chunks.append(bytes(chunk))
                elif chunk:
                    chunks.append(str(chunk).encode("utf-8", "replace"))
        except TypeError:
            chunks.append(str(raw).encode("utf-8", "replace"))
        return b"".join(chunks)


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
            updated_at=timezone.now(),
        )
        raise

    observed_ids = set()
    now = timezone.now()
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
