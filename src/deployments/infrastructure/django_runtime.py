"""Django adapter for operator-owned runtime and cluster selection."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from deployments.runtime import RuntimeRegistry, RuntimeSelection


def _value(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


class DjangoRuntimeSelectionResolver:
    """Resolve runtime policy with the operator-managed cluster record."""

    def __init__(self, registry: RuntimeRegistry | None = None) -> None:
        self.registry = registry or RuntimeRegistry.with_swarm()

    def resolve(
        self,
        *,
        service: Any = None,
        revision: Any = None,
        deployment: Any = None,
        policy: Any = None,
        cluster: Any = None,
        probe: bool = False,
    ) -> RuntimeSelection:
        if cluster is None:
            cluster = self._load_cluster(policy)
        return self.registry.resolve(
            service=service,
            revision=revision,
            deployment=deployment,
            policy=policy,
            cluster=cluster,
            probe=probe,
        )

    @staticmethod
    def _load_cluster(policy: Any) -> Any:
        """Load the declarative cluster row without making it mandatory."""
        from django.conf import settings
        from deploy.models import SwarmCluster

        cluster_name = (
            _value(policy, "cluster_name")
            or _value(policy, "cluster")
            or getattr(settings, "SWARM_CLUSTER_NAME", "")
            or os.environ.get("SWARM_CLUSTER_NAME", "")
            or "default"
        )
        return SwarmCluster.objects.filter(name=str(cluster_name)).first()


__all__ = ["DjangoRuntimeSelectionResolver"]
