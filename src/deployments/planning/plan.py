"""Immutable runtime-oriented deployment plans."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from deployments.core.runtime_graph import ServiceRuntimeGraph
from deployments.core.types import EndpointSpec, NetworkSpec, VolumeSpec
from deployments.runtime.capabilities import RuntimeCapability, StorageCapability
from deployments.runtime.contract import RuntimeIdentity, RuntimeSelection
from deployments.runtime.errors import RuntimeUnsupportedError
from deployments.runtime.execution_contract import RuntimeExecutionContract

from .configuration import ResolvedConfiguration
from .provenance import ConfigurationProvenance
from .policies import HealthPolicy, ReleaseSpec, RolloutStrategy


@dataclass(frozen=True)
class DeploymentPlan:
    """The normalized input consumed by a runtime adapter."""

    identity: RuntimeIdentity
    runtime_selection: RuntimeSelection
    process_graph: ServiceRuntimeGraph
    image_ref: str
    execution_contracts: Mapping[str, RuntimeExecutionContract] = field(default_factory=dict)
    artifact_digest: str = ""
    release_id: str | None = None
    strategy_kind: str = "application"
    environment: Mapping[str, str] = field(default_factory=dict)
    labels: Mapping[str, str] = field(default_factory=dict)
    secret_references: tuple[str, ...] = ()
    networks: tuple[NetworkSpec, ...] = ()
    volumes: tuple[VolumeSpec, ...] = ()
    endpoints: tuple[EndpointSpec, ...] = ()
    resources: Mapping[str, Any] = field(default_factory=dict)
    placement: tuple[str, ...] = ()
    runtime_options: Mapping[str, Any] = field(default_factory=dict)
    release_spec: Mapping[str, Any] = field(default_factory=dict)
    health_policy: Mapping[str, Any] = field(default_factory=dict)
    rollout_policy: Mapping[str, Any] = field(default_factory=dict)
    retry_policy: Mapping[str, Any] = field(default_factory=dict)
    logging_policy: Mapping[str, Any] = field(default_factory=dict)
    provenance: ConfigurationProvenance = field(default_factory=ConfigurationProvenance)
    deployment_config: Any | None = field(default=None, repr=False, compare=False)
    rollback_plan: "DeploymentPlan | None" = field(default=None, repr=False, compare=False)

    @property
    def required_capabilities(self) -> frozenset[RuntimeCapability]:
        return self.runtime_selection.required_capabilities

    def with_rollback_plan(self, rollback_plan: "DeploymentPlan") -> "DeploymentPlan":
        return replace(self, rollback_plan=rollback_plan)

    def public_summary(self) -> dict[str, Any]:
        return {
            "service_id": self.identity.service_id,
            "deployment_id": self.identity.deployment_id,
            "revision_id": self.identity.revision_id,
            "runtime": self.runtime_selection.backend,
            "strategy": self.strategy_kind,
            "cluster": self.runtime_selection.cluster,
            "image_ref": self.image_ref,
            "artifact_digest": self.artifact_digest,
            "release_id": self.release_id,
            "environment": {"keys": sorted(self.environment)},
            "labels": sorted(self.labels.keys()),
            "networks": [network.name for network in self.networks],
            "volumes": [volume.target for volume in self.volumes],
            "endpoints": [endpoint.name for endpoint in self.endpoints],
            "runtime_options": {"keys": sorted(self.runtime_options)},
            "execution_contracts": {
                name: contract.as_dict() for name, contract in self.execution_contracts.items()
            },
            "release_spec": {"configured": bool(self.release_spec)},
            "provenance": self.provenance.as_dict(),
        }


class DeploymentPlanCompiler:
    """Compile the existing runtime graph and config boundary into a plan."""

    def compile(
        self,
        *,
        identity: RuntimeIdentity,
        graph: ServiceRuntimeGraph,
        selection: RuntimeSelection,
        resolved: ResolvedConfiguration,
        image_ref: str,
        strategy_kind: str = "application",
        deployment_config: Any | None = None,
    ) -> DeploymentPlan:
        if not image_ref:
            raise ValueError("A deployment plan requires an image reference.")
        if strategy_kind not in {"application", "database", "specialized"}:
            raise ValueError(f"Unknown deployment strategy kind: {strategy_kind!r}.")

        required = {
            RuntimeCapability.SERVICE_SCHEDULING,
            RuntimeCapability.PROCESS_GRAPH,
        }
        if graph.processes:
            required.add(RuntimeCapability.REPLICAS)
        if graph.volumes:
            required.add(RuntimeCapability.PERSISTENT_VOLUMES)

        rollout_policy_raw = dict(resolved.get("rollout_policy") or {})
        runtime_options = dict(resolved.get("runtime_options") or {})
        graph_runtime = dict(graph.runtime or {})
        execution_contracts = dict(getattr(graph, "execution_contracts", {}) or {})
        primary_contract = (
            execution_contracts.get("web")
            or (next(iter(execution_contracts.values())) if execution_contracts else None)
        )
        if primary_contract is not None:
            runtime_options["execution_contract"] = primary_contract.as_dict()
            runtime_options["execution_contracts"] = {
                name: contract.as_dict()
                for name, contract in execution_contracts.items()
            }
            runtime_options["execution_contract_hashes"] = {
                "revision_contract_hash": primary_contract.contract_hash(),
                "plan_contract_hash": primary_contract.contract_hash(),
            }
            runtime_options["catalog_managed"] = bool(primary_contract.catalog_managed)
            runtime_options["image_entrypoint_owned"] = bool(primary_contract.image_entrypoint_owned)
        elif graph_runtime.get("image_entrypoint_owned"):
            runtime_options["catalog_managed"] = True
            runtime_options["image_entrypoint_owned"] = True

        # Keep the plan's compatibility runtime options aligned with the
        # normalized immutable graph. Legacy revision snapshots may still carry
        # runtime_options["processes"] with a stale shell wrapper; leaving that
        # nested list untouched lets downstream adapters bypass the corrected
        # RuntimeProcess objects above.
        if graph.processes:
            runtime_options["processes"] = [
                {
                    "name": str(process.name or "web"),
                    "process_type": str(process.process_type or "custom"),
                    "command": process.command,
                    "entrypoint": process.entrypoint,
                    "replicas": int(process.replicas or 1),
                    "enabled": bool(process.enabled),
                    "environment": dict(process.environment or {}),
                    "healthcheck": dict(process.healthcheck or {}),
                    "resources": dict(process.resources or {}),
                    "metadata": dict(process.metadata or {}),
                    "execution_contract": (
                        execution_contracts[process.name].as_dict()
                        if process.name in execution_contracts
                        else None
                    ),
                }
                for process in graph.processes
            ]
        RolloutStrategy.from_mapping(rollout_policy_raw)
        HealthPolicy.from_mapping(
            dict(resolved.get("health_policy") or runtime_options.get("healthcheck") or {})
        )
        release_spec = ReleaseSpec.from_mapping(dict(resolved.get("release_spec") or {}))
        if release_spec.command and release_spec.execution_backend not in {"runtime-entrypoint"}:
            raise RuntimeUnsupportedError(
                "This runtime does not have a safe release-command executor for the requested backend.",
                code="RELEASE_COMMAND_BACKEND_UNSUPPORTED",
                details={
                    "backend": release_spec.execution_backend,
                    "runtime": selection.backend,
                },
            )
        rollout_kind = str(rollout_policy_raw.get("kind") or "RECREATE").strip().upper()
        if rollout_kind == "ROLLING":
            required.add(RuntimeCapability.ROLLING_UPDATE)
        elif rollout_kind in {"CANARY", "BLUE_GREEN"}:
            required.add(RuntimeCapability.TRAFFIC_SPLITTING)
        if graph.networks:
            required.add(RuntimeCapability.OVERLAY_NETWORKS)
        if (
            graph.runtime.get("healthcheck")
            or resolved.get("healthcheck")
            or resolved.get("health_policy")
        ):
            required.add(RuntimeCapability.HEALTH_CHECKS)
        if runtime_options.get("placement_constraints"):
            required.add(RuntimeCapability.NODE_CONSTRAINTS)

        effective_selection = replace(
            selection,
            required_capabilities=frozenset(required),
        )

        storage_policy = dict(runtime_options.get("storage") or {})
        hard_capacity_requested = bool(storage_policy.get("hard_capacity"))
        if hard_capacity_requested and graph.volumes:
            if StorageCapability.HARD_CAPACITY not in effective_selection.capabilities.storage:
                raise RuntimeUnsupportedError(
                    "The selected runtime cannot provide a hard persistent-storage capacity guarantee.",
                    code="STORAGE_HARD_CAPACITY_UNSUPPORTED",
                    details={
                        "backend": effective_selection.backend,
                        "scope": "node_local" if effective_selection.backend == "swarm" else "runtime_local",
                        "requested": "hard_capacity",
                    },
                )
        missing = effective_selection.missing_capabilities
        if missing:
            raise RuntimeUnsupportedError(
                "The selected runtime cannot satisfy this deployment plan.",
                details={"missing": sorted(value.value for value in missing)},
            )

        environment = dict(
            resolved.get("environment")
            or graph.runtime_environment
            or getattr(deployment_config, "environment", {})
            or {}
        )
        networks = self._networks(
            resolved.get("networks"), graph.networks, deployment_config
        )
        volumes = self._volumes(
            resolved.get("volumes"), graph.volumes, deployment_config
        )
        endpoints = self._endpoints(
            resolved.get("endpoints"), graph.endpoints, deployment_config
        )
        resources = dict(
            resolved.get("resource_limits")
            or getattr(deployment_config, "resource_limits", {})
            or {}
        )
        health_policy = dict(
            resolved.get("health_policy")
            or runtime_options.get("healthcheck")
            or {}
        )
        return DeploymentPlan(
            identity=identity,
            runtime_selection=effective_selection,
            process_graph=graph,
            execution_contracts=execution_contracts,
            image_ref=str(image_ref),
            strategy_kind=strategy_kind,
            environment={str(key): str(value) for key, value in environment.items()},
            labels={str(key): str(value) for key, value in dict(resolved.get("labels") or {}).items()},
            secret_references=tuple(
                str(value) for value in (resolved.get("secret_references") or ())
            ),
            networks=tuple(networks),
            volumes=tuple(volumes),
            endpoints=tuple(endpoints),
            resources=copy.deepcopy(resources),
            placement=tuple(str(value) for value in (runtime_options.get("placement_constraints") or ())),
            runtime_options=copy.deepcopy(runtime_options),
            release_spec=copy.deepcopy(resolved.get("release_spec") or {}),
            health_policy=copy.deepcopy(health_policy),
            rollout_policy=copy.deepcopy(resolved.get("rollout_policy") or {}),
            retry_policy=copy.deepcopy(resolved.get("retry_policy") or {}),
            logging_policy=copy.deepcopy(resolved.get("logging_policy") or {}),
            provenance=resolved.provenance,
            deployment_config=deployment_config,
        )

    @staticmethod
    def _networks(raw: Any, graph_networks: tuple[str, ...], config: Any) -> list[NetworkSpec]:
        values = raw or graph_networks
        if not values:
            return list(getattr(config, "networks", ()) or ())
        existing = {
            str(network.name): network
            for network in (getattr(config, "networks", ()) or ())
        }
        result = []
        for value in values:
            if isinstance(value, NetworkSpec):
                result.append(value)
            else:
                name = str(value.get("name") if isinstance(value, Mapping) else value)
                result.append(existing.get(name) or NetworkSpec(name=name, driver="overlay"))
        return result

    @staticmethod
    def _volumes(raw: Any, graph_volumes: tuple[dict[str, Any], ...], config: Any) -> list[VolumeSpec]:
        values = raw or graph_volumes
        if not values:
            return list(getattr(config, "volumes", ()) or ())
        result = []
        for value in values:
            if isinstance(value, VolumeSpec):
                result.append(value)
            else:
                result.append(
                    VolumeSpec(
                        source=str(value.get("source") or ""),
                        target=str(value.get("target") or ""),
                        mode=str(value.get("mode") or "rw"),
                        mount_type=str(value.get("mount_type") or "volume"),
                        driver=str(value.get("driver") or "local"),
                        driver_opts=dict(value.get("driver_opts") or {}),
                        create=bool(value.get("create", True)),
                        size_mb=value.get("size_mb"),
                    )
                )
        return result

    @staticmethod
    def _endpoints(raw: Any, graph_endpoints: tuple[Any, ...], config: Any) -> list[EndpointSpec]:
        values = raw or graph_endpoints
        if not values:
            return list(getattr(config, "endpoints", ()) or ())
        result = []
        for value in values:
            if isinstance(value, EndpointSpec):
                result.append(value)
            elif isinstance(value, Mapping):
                result.append(EndpointSpec(**dict(value)))
            else:
                result.append(
                    EndpointSpec(
                        name=value.name,
                        target_port=value.target_port,
                        published_port=value.published_port,
                        protocol=value.protocol,
                        exposure=value.exposure,
                        hostname=value.hostname,
                        path=value.path,
                        tls=value.tls,
                        enabled=value.enabled,
                        process=value.process,
                        metadata=dict(value.metadata),
                    )
                )
        return result
