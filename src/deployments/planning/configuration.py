"""Explicit configuration precedence for deployment planning.

This module is intentionally framework-neutral.  Adapters can load Django,
Wagtail, model, or environment values and present them as named layers.  The
resolver owns precedence and rejects deployment-request values that belong to
operator policy.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from .provenance import ConfigurationProvenance, redact_value


class ConfigurationResolutionError(ValueError):
    """A configuration request cannot produce a safe effective policy."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "configuration_invalid",
        path: str = "",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.details = dict(details or {})


@dataclass(frozen=True)
class ConfigurationLayer:
    name: str
    values: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedConfiguration:
    values: Mapping[str, Any]
    provenance: ConfigurationProvenance

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def public_values(self) -> dict[str, Any]:
        return {
            str(key): redact_value(value, key=str(key))
            for key, value in self.values.items()
        }

    def explain(self, path: str) -> dict[str, Any] | None:
        return self.provenance.explain(path)


_MISSING = object()


def _flatten(values: Mapping[str, Any], prefix: str = ""):
    for key, value in values.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping) and value:
            yield from _flatten(value, path)
        else:
            yield path, copy.deepcopy(value)


def _unflatten(values: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path, value in values.items():
        target = result
        parts = path.split(".") if path else [path]
        for part in parts[:-1]:
            existing = target.get(part)
            if not isinstance(existing, dict):
                existing = {}
                target[part] = existing
            target = existing
        target[parts[-1]] = copy.deepcopy(value)
    return result


def _top_level(path: str) -> str:
    return path.split(".", 1)[0]


class ConfigurationResolver:
    """Resolve bounded configuration layers in documented order."""

    DEFAULT_ALLOWED_DEPLOYMENT_OVERRIDES = frozenset(
        {
            "environment",
            "runtime_options",
            "build_options",
            "start_command",
            "working_directory",
            "healthcheck_path",
            "healthcheck_expected_status",
            "healthcheck_timeout",
            "public_host",
            "url_handling",
        }
    )

    def __init__(
        self,
        *,
        defaults: Mapping[str, Any] | None = None,
        allowed_deployment_overrides: set[str] | frozenset[str] | None = None,
    ) -> None:
        self.defaults = dict(defaults or {})
        self.allowed_deployment_overrides = frozenset(
            allowed_deployment_overrides
            if allowed_deployment_overrides is not None
            else self.DEFAULT_ALLOWED_DEPLOYMENT_OVERRIDES
        )

    def resolve(
        self,
        *,
        platform_policy: Mapping[str, Any] | None = None,
        cluster_policy: Mapping[str, Any] | None = None,
        service_intent: Mapping[str, Any] | None = None,
        revision_snapshot: Mapping[str, Any] | None = None,
        deployment_overrides: Mapping[str, Any] | None = None,
    ) -> ResolvedConfiguration:
        layers = [
            ConfigurationLayer("platform_defaults", self.defaults),
            ConfigurationLayer("platform_policy", platform_policy or {}),
            ConfigurationLayer("cluster_policy", cluster_policy or {}),
            ConfigurationLayer("service_intent", service_intent or {}),
            ConfigurationLayer("revision_snapshot", revision_snapshot or {}),
        ]
        provenance = ConfigurationProvenance()
        flat: dict[str, Any] = {}
        requested: dict[str, Any] = {}

        for layer in layers:
            for path, value in _flatten(layer.values):
                flat[path] = value
                requested[path] = value
                provenance.record(path, source=layer.name, effective=value, requested=value)

        for path, value in _flatten(deployment_overrides or {}):
            if _top_level(path) not in self.allowed_deployment_overrides:
                provenance.reject(
                    path,
                    source="deployment_request",
                    reason="deployment request cannot override operator policy",
                )
                raise ConfigurationResolutionError(
                    f"Deployment override {path!r} is not permitted.",
                    code="deployment_override_forbidden",
                    path=path,
                )
            flat[path] = value
            requested[path] = value
            provenance.record(
                path,
                source="deployment_request",
                effective=value,
                requested=value,
            )

        values = _unflatten(flat)
        self._validate_policy_ceiling(
            values,
            platform_policy=platform_policy or {},
            cluster_policy=cluster_policy or {},
            provenance=provenance,
        )
        return ResolvedConfiguration(values=values, provenance=provenance)

    @staticmethod
    def _validate_policy_ceiling(
        values: Mapping[str, Any],
        *,
        platform_policy: Mapping[str, Any],
        cluster_policy: Mapping[str, Any],
        provenance: ConfigurationProvenance,
    ) -> None:
        requested = values.get("replicas")
        if requested is None:
            runtime_options = values.get("runtime_options") or {}
            requested = runtime_options.get("replicas")
        if requested in (None, ""):
            return
        try:
            requested_count = int(requested)
        except (TypeError, ValueError) as exc:
            raise ConfigurationResolutionError(
                "Replica count must be an integer.",
                code="invalid_replica_count",
                path="replicas",
            ) from exc

        ceilings = []
        for source_name, source in (
            ("platform_policy.max_replicas", platform_policy),
            ("cluster_policy.max_replicas", cluster_policy),
        ):
            raw = source.get("max_replicas")
            if raw in (None, ""):
                continue
            try:
                ceilings.append((source_name, int(raw)))
            except (TypeError, ValueError) as exc:
                raise ConfigurationResolutionError(
                    f"{source_name} must be an integer.",
                    code="invalid_replica_ceiling",
                    path="max_replicas",
                ) from exc
        if not ceilings:
            return
        ceiling_name, ceiling = min(ceilings, key=lambda item: item[1])
        if requested_count > ceiling:
            provenance.reject(
                "replicas",
                source="policy",
                reason=f"requested value exceeds {ceiling_name}={ceiling}",
            )
            raise ConfigurationResolutionError(
                f"Requested replicas {requested_count} exceed the effective policy ceiling {ceiling}.",
                code="policy_rejects_replicas",
                path="replicas",
                details={"requested": requested_count, "effective_max": ceiling},
            )
