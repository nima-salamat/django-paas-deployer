"""Authoritative runtime backend selection."""

from __future__ import annotations

import os
from typing import Any, Mapping

from .capabilities import (
    RuntimeAvailability,
    RuntimeAvailabilityState,
    RuntimeCapability,
    capability_set,
)
from .contract import RuntimeBackend, RuntimeContract, RuntimeSelection
from .errors import RuntimeUnsupportedError


def _value(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


class RuntimeRegistry:
    """Resolve one backend and expose its adapter without spreading flags."""

    def __init__(self, adapters: Mapping[str, RuntimeContract] | None = None) -> None:
        self._adapters = dict(adapters or {})

    @classmethod
    def with_swarm(cls, adapter: RuntimeContract | None = None) -> "RuntimeRegistry":
        if adapter is None:
            from .swarm.adapter import SwarmRuntimeAdapter

            adapter = SwarmRuntimeAdapter()
        return cls({RuntimeBackend.SWARM.value: adapter})

    def register(self, backend: str | RuntimeBackend, adapter: RuntimeContract) -> None:
        self._adapters[str(getattr(backend, "value", backend))] = adapter

    def adapter(self, backend: str | RuntimeBackend) -> RuntimeContract:
        key = str(getattr(backend, "value", backend))
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise RuntimeUnsupportedError(
                f"No runtime adapter is registered for backend {key!r}.",
                code="runtime_backend_unregistered",
                details={"backend": key},
            ) from exc

    def resolve(
        self,
        service: Any = None,
        revision: Any = None,
        deployment: Any = None,
        policy: Any = None,
        cluster: Any = None,
        *,
        required_capabilities: Any = None,
        probe: bool = False,
    ) -> RuntimeSelection:
        backend = self._resolve_backend(service, revision, deployment, policy, cluster)
        cluster_name = self._resolve_cluster(policy, cluster)
        required = capability_set(
            required_capabilities
            if required_capabilities is not None
            else _value(policy, "required_capabilities", ())
        )
        adapter = self._adapters.get(backend)
        if adapter is None:
            availability = RuntimeAvailability(
                backend=backend,
                state=RuntimeAvailabilityState.UNSUPPORTED,
                operator_enabled=False,
                reason_code="runtime_backend_unregistered",
                message=f"No runtime adapter is registered for backend {backend!r}.",
            )
            from .capabilities import RuntimeCapabilities

            capabilities = RuntimeCapabilities(backend=backend)
            return RuntimeSelection(
                backend=backend,
                cluster=cluster_name,
                required_capabilities=required,
                capabilities=capabilities,
                availability=availability,
                reason=self._selection_reason(policy, cluster, backend),
            )

        capabilities = adapter.describe_capabilities()
        availability = (
            adapter.check_availability(
                operator_enabled=self._operator_enabled(policy, cluster)
            )
            if probe
            else RuntimeAvailability(
                backend=backend,
                state=RuntimeAvailabilityState.UNKNOWN,
                operator_enabled=self._operator_enabled(policy, cluster),
                reason_code="availability_not_probed",
                message="Runtime availability was not probed during selection.",
            )
        )
        return RuntimeSelection(
            backend=backend,
            cluster=cluster_name,
            required_capabilities=required,
            capabilities=capabilities,
            availability=availability,
            reason=self._selection_reason(policy, cluster, backend),
        )

    def resolve_adapter(self, selection: RuntimeSelection) -> RuntimeContract:
        return self.adapter(selection.backend)

    @staticmethod
    def _resolve_backend(service: Any, revision: Any, deployment: Any, policy: Any, cluster: Any) -> str:
        # Backend choice is infrastructure policy, not executable tenant
        # configuration.  ``deployment``, ``revision`` and ``service`` are
        # intentionally not consulted here: allowing their ``backend`` field
        # to win would let a deployment request select host infrastructure.
        for source in (policy, cluster):
            value = _value(source, "runtime_backend") or _value(source, "backend")
            if value:
                return str(getattr(value, "value", value)).strip().lower()
        configured = os.environ.get("DEPLOYMENT_RUNTIME_BACKEND")
        if configured:
            return configured.strip().lower()
        # Compatibility input is read once by the registry.  Callers should
        # not continue branching on SWARM_ENABLED after adopting this class.
        raw = os.environ.get("SWARM_ENABLED")
        if raw is not None and raw.strip().lower() in {"0", "false", "no", "off"}:
            return RuntimeBackend.LEGACY_DOCKER.value
        return RuntimeBackend.SWARM.value

    @staticmethod
    def _resolve_cluster(policy: Any, cluster: Any) -> str | None:
        value = _value(policy, "cluster") or _value(policy, "cluster_name")
        value = value or _value(cluster, "name")
        if value:
            return str(value)
        return os.environ.get("SWARM_CLUSTER_NAME") or None

    @staticmethod
    def _operator_enabled(policy: Any, cluster: Any) -> bool:
        for source in (policy, cluster):
            value = _value(source, "operator_enabled", None)
            if value is None:
                value = _value(source, "enabled", None)
            if value is not None:
                return bool(value)
        return True

    @staticmethod
    def _selection_reason(policy: Any, cluster: Any, backend: str) -> str:
        if _value(policy, "backend") or _value(policy, "runtime_backend"):
            return "deployment policy"
        if _value(cluster, "backend") or _value(cluster, "runtime_backend"):
            return "cluster policy"
        if os.environ.get("DEPLOYMENT_RUNTIME_BACKEND"):
            return "bootstrap runtime backend"
        if os.environ.get("SWARM_ENABLED") is not None:
            return "legacy SWARM_ENABLED compatibility input"
        return f"default backend: {backend}"
