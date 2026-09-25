"""Immutable runtime-oriented deployment plans."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from deployments.core.runtime_graph import ServiceRuntimeGraph
from deployments.core.types import EndpointSpec, NetworkSpec, VolumeSpec
from deployments.runtime.capabilities import RuntimeCapability
from deployments.runtime.contract import RuntimeIdentity, RuntimeSelection
from deployments.runtime.errors import RuntimeUnsupportedError

from .configuration import ResolvedConfiguration
from .provenance import ConfigurationProvenance


@dataclass(frozen=True)
class DeploymentPlan:
    """The normalized input consumed by a runtime adapter."""

    identity: RuntimeIdentity
    runtime_selection: RuntimeSelection
    process_graph: ServiceRuntimeGraph
    image_ref: str
    environment: Mapping[str, str] = field(default_factory=dict)
    secret_references: tuple[str, ...] = ()
    networks: tuple[NetworkSpec, ...] = ()
    volumes: tuple[VolumeSpec, ...] = ()
    endpoints: tuple[EndpointSpec, ...] = ()
    resources: Mapping[str, Any] = field(default_factory=dict)
    placement: tuple[str, ...] = ()
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
            "cluster": self.runtime_selection.cluster,
            "image_ref": self.image_ref,
            "environment": {"keys": sorted(self.environment)},
            "networks": [network.name for network in self.networks],
            "volumes": [volume.target for volume in self.volumes],
            "endpoints": [endpoint.name for endpoint in self.endpoints],
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
        deployment_config: Any | None = None,
    ) -> DeploymentPlan:
        if not image_ref:
            raise ValueError("A deployment plan requires an image reference.")

        required = {
            RuntimeCapability.SERVICE_SCHEDULING,
            RuntimeCapability.PROCESS_GRAPH,
        }
        if graph.processes:
            required.add(RuntimeCapability.REPLICAS)
        if graph.volumes:
            required.add(RuntimeCapability.PERSISTENT_VOLUMES)
        if graph.networks:
            required.add(RuntimeCapability.OVERLAY_NETWORKS)
        if (
            graph.runtime.get("healthcheck")
            or resolved.get("healthcheck")
            or resolved.get("health_policy")
        ):
            required.add(RuntimeCapability.HEALTH_CHECKS)
        runtime_options = dict(resolved.get("runtime_options") or {})
        if runtime_options.get("placement_constraints"):
            required.add(RuntimeCapability.NODE_CONSTRAINTS)

        effective_selection = replace(
            selection,
            required_capabilities=frozenset(required),
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
            image_ref=str(image_ref),
            environment={str(key): str(value) for key, value in environment.items()},
            secret_references=tuple(
                str(value) for value in (resolved.get("secret_references") or ())
            ),
            networks=tuple(networks),
            volumes=tuple(volumes),
            endpoints=tuple(endpoints),
            resources=copy.deepcopy(resources),
            placement=tuple(str(value) for value in (runtime_options.get("placement_constraints") or ())),
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
