"""Immutable runtime specification and provenance snapshot."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping


_INLINE_SECRET_PATTERN = re.compile(
    r"(?i)(--?[a-z0-9_.-]*(?:password|passwd|secret|token|api[_-]?key|authorization|credential)[a-z0-9_.-]*"
    r"|(?:password|passwd|secret|token|api[_-]?key|authorization|credential|database_url|connection_string))"
    r"(\s*(?:=|:)\s*|\s+)(\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
)
_URL_PASSWORD_PATTERN = re.compile(r"(://[^:/@\s]+:)([^@/\s]+)(@)")


def _redact_inline_text(value: str, secret_values: tuple[str, ...] = ()) -> str:
    text = str(value)
    for secret in secret_values:
        if len(secret) >= 4:
            text = text.replace(secret, "[SECRET_REF]")
    text = _INLINE_SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[SECRET_REF]",
        text,
    )
    return _URL_PASSWORD_PATTERN.sub(r"\1[SECRET_REF]\3", text)


def _json_value(value: Any, secret_values: tuple[str, ...] = ()) -> Any:
    if isinstance(value, Mapping):
        return {
            str(k): "[SECRET_REF]" if _is_sensitive_key(str(k)) else _json_value(v, secret_values)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(v, secret_values) for v in value]
    if hasattr(value, "as_dict") and callable(value.as_dict):
        return _json_value(value.as_dict(), secret_values)
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return {str(k): _json_value(v, secret_values) for k, v in vars(value).items() if not str(k).startswith("_")}
    if isinstance(value, str):
        return _redact_inline_text(value, secret_values)
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(token in lowered for token in (
        "password", "secret", "token", "private_key",
        "api_key", "apikey", "authorization", "credential",
        "dsn", "database_url", "connection_string",
    ))


@dataclass(frozen=True)
class RuntimeSpec:
    image_ref: str
    image_digest: str = ""
    environment: Mapping[str, str] = field(default_factory=dict)
    secret_references: tuple[str, ...] = ()
    command: str | None = None
    entrypoint: str | None = None
    labels: Mapping[str, str] = field(default_factory=dict)
    networks: tuple[Mapping[str, Any], ...] = ()
    volumes: tuple[Mapping[str, Any], ...] = ()
    endpoints: tuple[Mapping[str, Any], ...] = ()
    read_only: bool = True
    resources: Mapping[str, Any] = field(default_factory=dict)
    health: Mapping[str, Any] = field(default_factory=dict)
    restart_policy: Mapping[str, Any] = field(default_factory=dict)
    host_config: Mapping[str, Any] = field(default_factory=dict)
    routing: Mapping[str, Any] = field(default_factory=dict)
    runtime_options: Mapping[str, Any] = field(default_factory=dict)
    source_revision: str = ""
    revision_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "image_ref": self.image_ref,
            "image_digest": self.image_digest,
            "environment": _json_value(dict(self.environment)),
            "secret_references": list(self.secret_references),
            "command": self.command,
            "entrypoint": self.entrypoint,
            "labels": _json_value(dict(self.labels)),
            "networks": _json_value(list(self.networks)),
            "volumes": _json_value(list(self.volumes)),
            "endpoints": _json_value(list(self.endpoints)),
            "read_only": self.read_only,
            "resources": _json_value(dict(self.resources)),
            "health": _json_value(dict(self.health)),
            "restart_policy": _json_value(dict(self.restart_policy)),
            "host_config": _json_value(dict(self.host_config)),
            "routing": _json_value(dict(self.routing)),
            "runtime_options": _json_value(dict(self.runtime_options)),
            "source_revision": self.source_revision,
            "revision_id": self.revision_id,
        }

    @property
    def sha256(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


    @classmethod
    def from_plan(cls, plan: Any, *, image_digest: str = "") -> "RuntimeSpec":
        """Build the immutable runtime snapshot directly from a native plan."""
        graph = getattr(plan, "process_graph", None)
        environment = {
            str(k): str(v)
            for k, v in dict(getattr(plan, "environment", {}) or {}).items()
        }
        secret_values = tuple(
            value for key, value in environment.items()
            if _is_sensitive_key(key) and value and value != "[SECRET_REF]"
        )
        processes = tuple(
            _json_value(item, secret_values)
            for item in (getattr(graph, "processes", ()) or ())
        )
        secret_references = tuple(
            sorted(str(v) for v in (getattr(plan, "secret_references", ()) or ()))
        )
        for key in list(environment):
            if _is_sensitive_key(key):
                environment[key] = "[SECRET_REF]"
        runtime_options = dict(getattr(plan, "runtime_options", {}) or {})
        runtime_options["processes"] = processes
        return cls(
            image_ref=str(getattr(plan, "image_ref", "") or ""),
            image_digest=str(image_digest or getattr(plan, "artifact_digest", "") or ""),
            environment=environment,
            secret_references=secret_references,
            command=None,
            entrypoint=None,
            labels={
                str(k): str(v)
                for k, v in dict(getattr(plan, "labels", {}) or {}).items()
            },
            networks=tuple(_json_value(value) for value in (getattr(plan, "networks", ()) or ())),
            volumes=tuple(_json_value(value) for value in (getattr(plan, "volumes", ()) or ())),
            endpoints=tuple(_json_value(value) for value in (getattr(plan, "endpoints", ()) or ())),
            read_only=bool(runtime_options.get("read_only", True)),
            resources=_json_value(dict(getattr(plan, "resources", {}) or {})),
            health=_json_value(dict(getattr(plan, "health_policy", {}) or {})),
            restart_policy=_json_value(dict(runtime_options.get("restart_policy") or {})),
            host_config=_json_value(dict(runtime_options.get("host_config") or {})),
            routing=_json_value(dict(runtime_options.get("routing") or {})),
            runtime_options=_json_value(runtime_options, secret_values),
            source_revision=str(getattr(getattr(plan, "identity", None), "revision_id", "") or ""),
            revision_id=str(getattr(getattr(plan, "identity", None), "revision_id", "") or ""),
        )

    @classmethod
    def from_config(
        cls,
        config: Any,
        *,
        image_ref: str | None = None,
        image_digest: str = "",
        source_revision: str = "",
        revision_id: str = "",
    ) -> "RuntimeSpec":
        networks = tuple(_json_value(vars(v) if hasattr(v, "__dict__") else v) for v in (getattr(config, "networks", ()) or ()))
        volumes = tuple(_json_value(vars(v) if hasattr(v, "__dict__") else v) for v in (getattr(config, "volumes", ()) or ()))
        endpoints = tuple(_json_value(vars(v) if hasattr(v, "__dict__") else v) for v in (getattr(config, "endpoints", ()) or ()))
        runtime_options = dict(getattr(config, "runtime_options", {}) or {})
        raw_environment = {
            str(k): str(v)
            for k, v in dict(getattr(config, "environment", {}) or {}).items()
        }
        secret_values = tuple(value for key, value in raw_environment.items() if _is_sensitive_key(key) and value)
        secret_references = []
        for key in list(raw_environment):
            lowered = key.lower()
            if any(token in lowered for token in ("password", "secret", "token", "private_key", "api_key", "apikey", "authorization", "credential")):
                raw_environment[key] = "[SECRET_REF]"
                secret_references.append(key)
        return cls(
            image_ref=str(image_ref or getattr(config, "image_ref", "") or ""),
            image_digest=str(image_digest or ""),
            environment=raw_environment,
            secret_references=tuple(sorted(secret_references)),
            command=_redact_inline_text(str(getattr(config, "start_command", "") or ""), secret_values) or None,
            entrypoint=_redact_inline_text(str(getattr(config, "entry_point", "") or ""), secret_values) or None,
            labels={str(k): str(v) for k, v in dict(getattr(config, "labels", {}) or {}).items()},
            networks=networks,
            volumes=volumes,
            endpoints=endpoints,
            read_only=bool(getattr(config, "read_only", True)),
            resources=dict(getattr(config, "resource_limits", {}) or {}),
            health={
                "path": getattr(config, "healthcheck_path", None),
                "expected_status": list(getattr(config, "healthcheck_expected_status", ()) or ()),
                "timeout": getattr(config, "healthcheck_timeout", None),
                "interval": getattr(config, "health_interval", None),
            },
            restart_policy=dict(runtime_options.get("restart_policy") or {}),
            host_config={
                "exposed_ports": _json_value(runtime_options.get("exposed_ports") or {}),
                "port_bindings": _json_value(runtime_options.get("port_bindings") or {}),
            },
            routing={
                "public_host": getattr(config, "public_host", None),
                "port": getattr(config, "port", None),
            },
            runtime_options=_json_value(runtime_options, secret_values),
            source_revision=source_revision,
            revision_id=revision_id,
        )

__all__ = ["RuntimeSpec"]
