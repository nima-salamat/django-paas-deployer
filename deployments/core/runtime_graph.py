"""Normalized runtime graph for the deployment executor.

Input adapters (Compose, catalog, Git/archive platform detection, existing
image) converge on this graph before Docker execution. The graph contains
desired runtime semantics only; Docker API objects never appear here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class RuntimeEndpoint:
    name: str
    target_port: int
    published_port: int | None = None
    protocol: str = "tcp"
    exposure: str = "internal"
    hostname: str = ""
    path: str = ""
    tls: bool = False
    enabled: bool = True
    process: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def host_published(self) -> bool:
        return self.enabled and self.published_port is not None

    @property
    def public(self) -> bool:
        return self.enabled and self.exposure == "public"


@dataclass(frozen=True)
class RuntimeProcess:
    name: str
    process_type: str
    command: str | None = None
    entrypoint: str | None = None
    replicas: int = 1
    enabled: bool = True
    environment: dict[str, str] = field(default_factory=dict)
    healthcheck: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ServiceRuntimeGraph:
    source: dict[str, Any] = field(default_factory=dict)
    build: dict[str, Any] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=dict)
    build_environment: dict[str, str] = field(default_factory=dict)
    runtime_environment: dict[str, str] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)
    processes: tuple[RuntimeProcess, ...] = ()
    endpoints: tuple[RuntimeEndpoint, ...] = ()
    volumes: tuple[dict[str, Any], ...] = ()
    networks: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_revision(cls, revision) -> "ServiceRuntimeGraph":
        process_rows = []
        for raw in revision.process_snapshot or []:
            process_rows.append(
                RuntimeProcess(
                    name=str(raw.get("name") or "web"),
                    process_type=str(raw.get("process_type") or "custom"),
                    command=raw.get("command"),
                    entrypoint=raw.get("entrypoint"),
                    replicas=max(1, int(raw.get("replicas") or 1)),
                    enabled=bool(raw.get("enabled", True)),
                    environment={str(k): str(v) for k, v in (raw.get("environment") or {}).items()},
                    healthcheck=dict(raw.get("healthcheck") or {}),
                    resources=dict(raw.get("resources") or {}),
                    metadata=dict(raw.get("metadata") or {}),
                )
            )

        endpoint_rows = []
        for raw in revision.endpoint_snapshot or []:
            endpoint_rows.append(
                RuntimeEndpoint(
                    name=str(raw.get("name") or "endpoint"),
                    target_port=int(raw["target_port"]),
                    published_port=int(raw["published_port"]) if raw.get("published_port") not in (None, "") else None,
                    protocol=str(raw.get("protocol") or "tcp").lower(),
                    exposure=str(raw.get("exposure") or "internal").lower(),
                    hostname=str(raw.get("hostname") or ""),
                    path=str(raw.get("path") or ""),
                    tls=bool(raw.get("tls", False)),
                    enabled=bool(raw.get("enabled", True)),
                    process=str(raw.get("process")) if raw.get("process") else None,
                    metadata=dict(raw.get("metadata") or {}),
                )
            )

        build_environment: dict[str, str] = {}
        runtime_environment: dict[str, str] = {}
        for key, item in (revision.environment_snapshot or {}).items():
            value = str(item.get("value") if isinstance(item, dict) else item)
            scope = str(item.get("scope") if isinstance(item, dict) else "runtime").lower()
            if scope in {"build", "both"}:
                build_environment[str(key)] = value
            if scope in {"runtime", "both"}:
                runtime_environment[str(key)] = value

        return cls(
            source=dict(revision.source_snapshot or {}),
            build=dict(revision.build_snapshot or {}),
            runtime=dict(revision.runtime_snapshot or {}),
            build_environment=build_environment,
            runtime_environment=runtime_environment,
            environment=runtime_environment,

            processes=tuple(process_rows),
            endpoints=tuple(endpoint_rows),
            volumes=tuple(dict(v) for v in (revision.volume_snapshot or [])),
            networks=tuple(str(n) for n in (revision.network_snapshot or [])),
            metadata={"revision_id": str(revision.pk), "revision": revision.revision_number},
        )

    def enabled_endpoints(self) -> tuple[RuntimeEndpoint, ...]:
        return tuple(endpoint for endpoint in self.endpoints if endpoint.enabled)

    def primary_public_endpoint(self) -> RuntimeEndpoint | None:
        candidates = [
            endpoint for endpoint in self.enabled_endpoints()
            if endpoint.public and endpoint.protocol in {"http", "https", "ws"}
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda endpoint: (endpoint.protocol not in {"http", "https"}, endpoint.name))
        return candidates[0]

    def exposed_ports(self) -> dict[str, dict]:
        ports: dict[str, dict] = {}
        for endpoint in self.enabled_endpoints():
            ports[f"{endpoint.target_port}/{endpoint.protocol}"] = {}
        return ports

    def port_bindings(self) -> dict[str, list[dict[str, str]]]:
        bindings: dict[str, list[dict[str, str]]] = {}
        for endpoint in self.enabled_endpoints():
            if endpoint.published_port is None:
                continue
            key = f"{endpoint.target_port}/{endpoint.protocol}"
            bindings[key] = [{"HostPort": str(endpoint.published_port)}]
        return bindings

    def public_endpoints(self) -> list[dict[str, Any]]:
        return [
            {
                "name": endpoint.name,
                "target_port": endpoint.target_port,
                "protocol": endpoint.protocol,
                "hostname": endpoint.hostname,
                "path": endpoint.path,
                "tls": endpoint.tls,
            }
            for endpoint in self.enabled_endpoints()
            if endpoint.public
        ]
