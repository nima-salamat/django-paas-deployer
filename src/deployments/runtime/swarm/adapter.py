"""Native runtime adapter translating DeploymentPlan into Swarm execution inputs.

The adapter owns the runtime-neutral contract boundary. Concrete Docker/Swarm
operations remain implemented by deployments.core.swarm.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable

from deployments.common.exceptions import DeploymentError
from deployments.core.swarm import SwarmRuntime, SwarmServiceState, swarm_enabled

from ..artifacts import ArtifactReference, SwarmArtifactRegistry
from ..capabilities import (
    RuntimeAvailability,
    RuntimeAvailabilityState,
    RuntimeCapabilities,
    RuntimeCapability,
)
from ..contract import (
    RuntimeBackend,
    RuntimeContract,
    RuntimeHandle,
    RuntimeIdentity,
    RuntimeOperationResult,
)
from ..errors import RuntimeOperationError, RuntimeUnavailableError, RuntimeUnsupportedError
from ..observations import (
    RuntimeObservation,
    RuntimeObservedStatus,
    RuntimeTaskObservation,
)


@dataclass(frozen=True)
class SwarmExecutionSpec:
    """Typed Swarm backend input compiled from the native DeploymentPlan."""
    name: str
    tag: str = "release"
    image_ref: str = ""
    environment: dict[str, str] = field(default_factory=dict)
    start_command: Any = None
    entry_point: Any = None
    working_directory: str = "/app"
    read_only: bool = True
    resource_limits: dict[str, Any] = field(default_factory=dict)
    runtime_options: dict[str, Any] = field(default_factory=dict)
    networks: tuple[Any, ...] = ()
    volumes: tuple[Any, ...] = ()
    endpoints: tuple[Any, ...] = ()
    labels: dict[str, str] = field(default_factory=dict)
    public_host: str | None = None
    health_timeout: float = 60.0
    process: Any = None


class SwarmRuntimeAdapter:
    """Expose the current Swarm runtime through the runtime contract."""

    backend = RuntimeBackend.SWARM.value

    def __init__(
        self,
        *,
        runtime: SwarmRuntime | None = None,
        runtime_factory: Callable[[], SwarmRuntime] | None = None,
        operator_enabled: bool | None = None,
    ) -> None:
        self._runtime = runtime
        self._runtime_factory = runtime_factory or SwarmRuntime
        self._operator_enabled = operator_enabled
        self._artifact_registry = None

    @property
    def artifact_registry(self) -> SwarmArtifactRegistry:
        if self._artifact_registry is None:
            self._artifact_registry = SwarmArtifactRegistry(self.runtime)
        return self._artifact_registry

    @property
    def runtime(self) -> SwarmRuntime:
        if self._runtime is None:
            self._runtime = self._runtime_factory()
        return self._runtime

    def describe_capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            backend=self.backend,
            supported=frozenset(
                {
                    RuntimeCapability.SERVICE_SCHEDULING,
                    RuntimeCapability.REPLICAS,
                    RuntimeCapability.ROLLING_UPDATE,
                    RuntimeCapability.ROLLBACK,
                    RuntimeCapability.NODE_CONSTRAINTS,
                    RuntimeCapability.OVERLAY_NETWORKS,
                    RuntimeCapability.PERSISTENT_VOLUMES,
                    RuntimeCapability.SERVICE_LOGS,
                    RuntimeCapability.HEALTH_CHECKS,
                    RuntimeCapability.PROCESS_GRAPH,
                }
            ),
            metadata={"replica_limit": "0..8", "adapter": "swarm-runtime"},
        )

    def check_availability(
        self, *, operator_enabled: bool | None = None
    ) -> RuntimeAvailability:
        enabled = (
            self._operator_enabled
            if operator_enabled is None and self._operator_enabled is not None
            else operator_enabled
        )
        if enabled is None:
            enabled = swarm_enabled()
        if not enabled:
            return RuntimeAvailability(
                backend=self.backend,
                state=RuntimeAvailabilityState.DISABLED,
                operator_enabled=False,
                reason_code="runtime_disabled",
                message="Docker Swarm runtime is disabled by operator/bootstrap policy.",
            )
        try:
            swarm = self.runtime.assert_active()
        except DeploymentError as exc:
            code = str(getattr(exc, "code", "") or "runtime_unavailable")
            if code == "SWARM_DISABLED":
                state = RuntimeAvailabilityState.DISABLED
                reachable = False
                manager = False
            elif code == "DOCKER_UNAVAILABLE":
                state = RuntimeAvailabilityState.UNAVAILABLE
                reachable = False
                manager = False
            elif code in {"SWARM_NOT_ACTIVE", "SWARM_NOT_MANAGER"}:
                state = RuntimeAvailabilityState.DEGRADED
                reachable = True
                manager = code != "SWARM_NOT_MANAGER"
            else:
                state = RuntimeAvailabilityState.UNAVAILABLE
                reachable = False
                manager = False
            return RuntimeAvailability(
                backend=self.backend,
                state=state,
                operator_enabled=True,
                reachable=reachable,
                manager_capable=manager,
                reason_code=code.lower(),
                message=str(getattr(exc, "user_message", None) or exc),
                details=getattr(exc, "details", {}) or {},
            )
        except Exception as exc:  # Docker SDK versions may expose other errors.
            return RuntimeAvailability(
                backend=self.backend,
                state=RuntimeAvailabilityState.UNAVAILABLE,
                operator_enabled=True,
                reason_code="runtime_probe_failed",
                message=str(exc),
            )
        return RuntimeAvailability(
            backend=self.backend,
            state=RuntimeAvailabilityState.ACTIVE,
            operator_enabled=True,
            reachable=True,
            manager_capable=bool((swarm or {}).get("ControlAvailable")),
            reason_code="",
            message="Docker Swarm manager is active.",
            details={"local_node_state": (swarm or {}).get("LocalNodeState")},
        )

    @staticmethod
    def _identity(plan: Any) -> RuntimeIdentity:
        value = getattr(plan, "identity", plan)
        if isinstance(value, RuntimeIdentity):
            return value
        return RuntimeIdentity(
            service_id=str(getattr(value, "service_id", "service")),
            deployment_id=getattr(value, "deployment_id", None),
            revision_id=getattr(value, "revision_id", None),
            process_name=str(getattr(value, "process_name", "web")),
            runtime_name=str(getattr(value, "runtime_name", "") or ""),
        )

    @staticmethod
    def _plan_config(plan: Any) -> tuple[SwarmExecutionSpec, str]:
        """Compile a native DeploymentPlan into a typed Swarm backend request."""
        image_ref = str(getattr(plan, "image_ref", "") or "")
        identity = SwarmRuntimeAdapter._identity(plan)
        if not image_ref:
            raise RuntimeOperationError(
                "The deployment plan does not contain an application artifact reference.",
                code="swarm_artifact_reference_missing",
                category="runtime_contract",
            )
        graph = getattr(plan, "process_graph", None)
        processes = list(getattr(graph, "processes", ()) or ())
        primary = next(
            (item for item in processes if str(getattr(item, "name", "")).lower() == "web"),
            processes[0] if processes else None,
        )
        runtime_options = dict(getattr(plan, "runtime_options", {}) or {})
        runtime_options.setdefault(
            "processes",
            [
                {
                    "name": str(getattr(item, "name", "web") or "web"),
                    "process_type": str(getattr(item, "process_type", "custom") or "custom"),
                    "command": getattr(item, "command", None),
                    "entrypoint": getattr(item, "entrypoint", None),
                    "replicas": int(getattr(item, "replicas", 1) or 1),
                    "enabled": bool(getattr(item, "enabled", True)),
                    "environment": dict(getattr(item, "environment", {}) or {}),
                    "healthcheck": dict(getattr(item, "healthcheck", {}) or {}),
                    "resources": dict(getattr(item, "resources", {}) or {}),
                    "metadata": dict(getattr(item, "metadata", {}) or {}),
                }
                for item in processes
            ],
        )
        labels = {str(k): str(v) for k, v in dict(getattr(plan, "labels", {}) or {}).items()}
        labels.update({
            "passdeployer.service": identity.service_id,
            "passdeployer.deployment": str(identity.deployment_id or ""),
            "passdeployer.process": str(getattr(primary, "name", "web") or "web"),
            "release.id": str(getattr(plan, "release_id", "") or ""),
            "revision.id": str(identity.revision_id or ""),
            "artifact.digest": str(getattr(plan, "artifact_digest", "") or ""),
        })
        routing = dict(runtime_options.get("routing") or {})
        health = dict(getattr(plan, "health_policy", {}) or {})
        spec = SwarmExecutionSpec(
            name=identity.runtime_name or identity.service_id,
            tag=(image_ref.rsplit(":", 1)[-1] if ":" in image_ref and "@" not in image_ref else "release"),
            image_ref=image_ref,
            environment={
                str(k): str(v)
                for k, v in dict(getattr(plan, "environment", {}) or {}).items()
            },
            start_command=getattr(primary, "command", None) if primary is not None else None,
            entry_point=getattr(primary, "entrypoint", None) if primary is not None else None,
            working_directory=str(runtime_options.get("working_directory") or "/app"),
            read_only=bool(runtime_options.get("read_only", True)),
            resource_limits=dict(getattr(plan, "resources", {}) or {}),
            runtime_options=runtime_options,
            networks=tuple(getattr(plan, "networks", ()) or ()),
            volumes=tuple(getattr(plan, "volumes", ()) or ()),
            endpoints=tuple(getattr(plan, "endpoints", ()) or ()),
            labels=labels,
            public_host=str(routing.get("public_host") or "") or None,
            health_timeout=float(health.get("timeout") or 60.0),
        )
        return spec, image_ref

    @staticmethod
    def _ensure_available(adapter: "SwarmRuntimeAdapter") -> None:
        availability = adapter.check_availability()
        if not availability.can_execute:
            if availability.state == RuntimeAvailabilityState.DISABLED:
                raise RuntimeUnavailableError(
                    availability.message,
                    code="runtime_disabled",
                    recoverable=False,
                )
            raise RuntimeUnavailableError(
                availability.message or "Docker Swarm is unavailable.",
                code=availability.reason_code or "runtime_unavailable",
                details=availability.details,
            )

    def apply(self, plan: Any, *, operation_key: str, cancel_check: Callable[[], bool] | None = None) -> RuntimeOperationResult:
        self._ensure_available(self)
        config, image_ref = self._plan_config(plan)
        identity = self._identity(plan)
        artifact_digest = str(getattr(plan, "artifact_digest", "") or "")
        if artifact_digest:
            published = self.artifact_registry.ensure_available(
                ArtifactReference(
                    digest=artifact_digest,
                    image_ref=image_ref,
                    source_digest=str(getattr(plan, "source_digest", "") or ""),
                ),
                service_name=config.name,
                tag=config.tag,
                operation_key=operation_key,
            )
            image_ref = published.image_ref
        try:
            apply_processes = getattr(self.runtime, "apply_processes", None)
            if callable(apply_processes):
                states = apply_processes(
                    config,
                    image_ref=image_ref,
                    operation_key=operation_key,
                    cancel_check=cancel_check,
                    prepared_image_ref=image_ref,
                )
                process_names = tuple(
                    str(state.name) for state in states.values()
                    if getattr(state, "name", None)
                )
                state = states.get("web") or next(iter(states.values()))
            else:
                # Small legacy test doubles/non-process runtimes may only expose
                # single-service apply. Production SwarmRuntime always exposes
                # apply_processes.
                state = self.runtime.apply(
                    config,
                    image_ref=image_ref,
                )
                process_names = (str(getattr(state, "name", config.name)),)
        except DeploymentError as exc:
            raise RuntimeOperationError(
                str(exc),
                code=str(getattr(exc, "code", "swarm_apply_failed") or "swarm_apply_failed").lower(),
                recoverable=bool(getattr(exc, "recoverable", False)),
                category=str(getattr(exc, "category", "runtime_error") or "runtime_error"),
                details=getattr(exc, "details", {}) or {},
                user_message=getattr(exc, "user_message", None),
            ) from exc
        observation = self._observation(identity, state, assume_identity_revision=True)
        handle = RuntimeHandle(
            backend=self.backend,
            identity=identity,
            runtime_id=observation.runtime_id,
            resource_name=identity.resource_name(),
            metadata={
                "service_names": process_names,
                "service_ids": {
                    str(name): str(getattr(result, "service_id", "") or "")
                    for name, result in states.items()
                },
            },
        )
        return RuntimeOperationResult(
            success=True,
            changed=True,
            handle=handle,
            observation=observation,
            details={"operation_key": operation_key, "service_names": process_names},
        )

    def inspect(self, identity: RuntimeIdentity) -> RuntimeObservation:
        self._ensure_available(self)
        try:
            state = self.runtime.inspect_service(identity.resource_name())
        except DeploymentError as exc:
            raise RuntimeOperationError(
                str(exc),
                code=str(getattr(exc, "code", "swarm_inspect_failed") or "swarm_inspect_failed").lower(),
                recoverable=bool(getattr(exc, "recoverable", False)),
            ) from exc
        # Inspection is observed state, not desired state. If an externally
        # created service has no managed revision label, keep the revision
        # unknown so reconciliation can request operator intervention instead
        # of silently declaring it converged.
        return self._observation(identity, state, assume_identity_revision=False)

    def wait_ready(
        self,
        handle: RuntimeHandle,
        *,
        timeout: float | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> RuntimeOperationResult:
        self._ensure_available(self)
        if cancel_check is not None and cancel_check():
            raise RuntimeOperationError(
                "Runtime readiness was cancelled.",
                code="runtime_cancelled",
                category="cancellation",
            )
        try:
            process_names = tuple(
                str(item) for item in (handle.metadata.get("service_names") or ())
                if str(item).strip()
            ) or (handle.resource_name or handle.identity.resource_name(),)
            import time
            deadline = time.monotonic() + float(timeout or 60)
            states = {}
            for service_name in process_names:
                remaining = max(0.0, deadline - time.monotonic())
                if cancel_check is not None and cancel_check():
                    raise RuntimeOperationError(
                        "Runtime readiness was cancelled.",
                        code="runtime_cancelled",
                        category="cancellation",
                    )
                states[service_name] = self.runtime.wait_ready(
                    service_name,
                    timeout=remaining,
                    cancel_check=cancel_check,
                )
            state = states.get(handle.resource_name or "") or next(iter(states.values()))
        except DeploymentError as exc:
            raise RuntimeOperationError(
                str(exc),
                code=str(getattr(exc, "code", "swarm_readiness_failed") or "swarm_readiness_failed").lower(),
                recoverable=bool(getattr(exc, "recoverable", False)),
                details=getattr(exc, "details", {}) or {},
                user_message=getattr(exc, "user_message", None),
            ) from exc
        observation = self._observation(handle.identity, state, assume_identity_revision=True)
        return RuntimeOperationResult(success=True, changed=True, handle=handle, observation=observation, details={"processes": sorted(process_names)})

    def stop(self, handle: RuntimeHandle, *, operation_key: str) -> RuntimeOperationResult:
        self._ensure_available(self)
        self.runtime.stop(handle.resource_name or handle.identity.resource_name(), service_id=handle.identity.service_id, operation_key=operation_key)
        return RuntimeOperationResult(success=True, changed=True, handle=handle, details={"operation_key": operation_key})

    def remove(self, handle: RuntimeHandle, *, operation_key: str) -> RuntimeOperationResult:
        self._ensure_available(self)
        self.runtime.remove(handle.resource_name or handle.identity.resource_name(), service_id=handle.identity.service_id, operation_key=operation_key)
        return RuntimeOperationResult(success=True, changed=True, handle=handle, details={"operation_key": operation_key})

    def rollback(
        self,
        plan: Any,
        *,
        operation_key: str,
        target_plan: Any | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> RuntimeOperationResult:
        rollback_plan = target_plan or getattr(plan, "rollback_plan", None)
        if rollback_plan is None:
            raise RuntimeUnsupportedError(
                "Swarm rollback requires an explicit previously-known-good plan.",
                code="swarm_rollback_plan_required",
            )
        return self.apply(rollback_plan, operation_key=operation_key, cancel_check=cancel_check)

    def restart_service_group(self, service_id: str) -> RuntimeOperationResult:
        self._ensure_available(self)
        self.runtime.restart_service_group(str(service_id))
        return RuntimeOperationResult(success=True, changed=True, details={"service_id": str(service_id)})

    def logs(self, identity: RuntimeIdentity, *, tail: int | str = 200) -> Any:
        self._ensure_available(self)
        return self.runtime.service_logs(identity.resource_name(), tail=tail)

    @staticmethod
    def _observation(
        identity: RuntimeIdentity,
        state: SwarmServiceState | None,
        *,
        assume_identity_revision: bool = False,
    ) -> RuntimeObservation:
        if state is None:
            return RuntimeObservation(identity=identity, status=RuntimeObservedStatus.MISSING)
        tasks = tuple(
            RuntimeTaskObservation(
                task_id=item.task_id,
                desired_state=item.desired_state,
                state=item.state,
                node_id=item.node_id,
                node_name=item.node_name,
                error=item.error,
                message=item.message,
                health_status=item.health_status,
            )
            for item in state.tasks
        )
        running_ready = state.replicas_desired == state.replicas_running and state.replicas_running > 0
        if state.healthcheck_configured:
            healthy_tasks = [
                task for task in state.tasks
                if str(task.health_status or "").lower() == "healthy"
            ]
            ready = running_ready and len(healthy_tasks) >= state.replicas_desired
        else:
            ready = running_ready

        if ready:
            status = RuntimeObservedStatus.READY
        elif any(task.state.lower() in {"failed", "rejected"} for task in state.tasks):
            status = RuntimeObservedStatus.FAILED
        elif any(task.state.lower() == "running" for task in state.tasks):
            status = RuntimeObservedStatus.DEGRADED
        else:
            status = RuntimeObservedStatus.PROVISIONING
        labels = dict(state.labels or {})
        observed_revision = (
            labels.get("revision.id")
            or labels.get("passdeployer.revision")
            or (identity.revision_id if assume_identity_revision else None)
        )
        return RuntimeObservation(
            identity=replace(identity, revision_id=observed_revision),
            status=status,
            runtime_id=state.service_id,
            desired_replicas=state.replicas_desired,
            ready_replicas=state.replicas_running,
            tasks=tasks,
            details={"service_name": state.name, "labels": labels},
        )
