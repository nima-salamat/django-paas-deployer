"""Normalized runtime graph for the deployment executor.

Input adapters (Compose, catalog, Git/archive platform detection, existing
image) converge on this graph before Docker execution. The graph contains
desired runtime semantics only; Docker API objects never appear here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable

from deployments.runtime.execution_contract import RuntimeExecutionContract


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


def _dockerfile_default_cmd(dockerfile: str) -> str | None:
    """Extract the final Dockerfile CMD without executing or mutating the artifact."""
    matches = list(
        re.finditer(
            r"^\s*CMD\s+(.+)$",
            dockerfile or "",
            flags=re.MULTILINE | re.IGNORECASE,
        )
    )
    if not matches:
        return None

    raw = matches[-1].group(1).strip()
    if not raw:
        return None

    if raw.startswith("["):
        try:
            import json
            import shlex
            values = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if isinstance(values, list) and values and all(isinstance(item, str) for item in values):
            return shlex.join(values)
        return None

    return raw


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
    execution_contracts: dict[str, RuntimeExecutionContract] = field(default_factory=dict)

    @property
    def execution_contract(self) -> RuntimeExecutionContract | None:
        if not self.execution_contracts:
            return None
        return self.execution_contracts.get("web") or next(iter(self.execution_contracts.values()))

    @classmethod
    def from_revision(cls, revision) -> "ServiceRuntimeGraph":
        # Catalog Dockerfiles may own an image-level ENTRYPOINT. Older
        # revisions stored that Dockerfile instruction in ServiceProcess.entrypoint,
        # but the native Swarm contract treats process.entrypoint as an effective
        # runtime command override. Detect and discard that stale value here so
        # existing installations converge to the same semantics as new ones.
        config_snapshot = dict(getattr(revision, "config_snapshot", None) or {})
        build_snapshot = dict(getattr(revision, "build_snapshot", None) or {})
        runtime_snapshot = dict(getattr(revision, "runtime_snapshot", None) or {})
        source_snapshot = dict(getattr(revision, "source_snapshot", None) or {})
        source_kind = str(config_snapshot.get("source_kind") or "").strip().lower()
        catalog_managed = (
            source_kind == "catalog"
            or bool(config_snapshot.get("catalog_managed"))
            or bool(source_snapshot.get("catalog_id"))
        )
        dockerfile = str(
            build_snapshot.get("dockerfile")
            or config_snapshot.get("dockerfile")
            or ""
        )
        dockerfile_owns_entrypoint = bool(
            catalog_managed
            and re.search(
                r"^\s*ENTRYPOINT\s+",
                dockerfile,
                flags=re.MULTILINE | re.IGNORECASE,
            )
        )

        runtime = dict(runtime_snapshot)
        if dockerfile_owns_entrypoint:
            runtime["catalog_managed"] = True
            runtime["image_entrypoint_owned"] = True

        dockerfile_default_cmd = (
            _dockerfile_default_cmd(dockerfile)
            if dockerfile_owns_entrypoint
            else None
        )

        process_rows = []
        execution_contracts: dict[str, RuntimeExecutionContract] = {}
        for raw in (getattr(revision, "process_snapshot", None) or []):
            command = raw.get("command")
            entrypoint = raw.get("entrypoint")

            # For a catalog image that owns ENTRYPOINT, Dockerfile CMD is the
            # executable authority. Legacy ServiceProcess/runtime snapshots can
            # contain an explicit but stale shell wrapper (for example /bin/sh -lc
            # ...) that shadows the immutable image CMD and makes Swarm execute a
            # command that is absent from the artifact.
            if catalog_managed and dockerfile_owns_entrypoint and dockerfile_default_cmd:
                command = dockerfile_default_cmd

            if dockerfile_owns_entrypoint:
                entrypoint = None
            process = RuntimeProcess(
                name=str(raw.get("name") or "web"),
                process_type=str(raw.get("process_type") or "custom"),
                command=command,
                entrypoint=entrypoint,
                replicas=int(raw.get("replicas") or 1),
                enabled=bool(raw.get("enabled", True)),
                environment={str(k): str(v) for k, v in (raw.get("environment") or {}).items()},
                healthcheck=dict(raw.get("healthcheck") or {}),
                resources=dict(raw.get("resources") or {}),
                metadata=dict(raw.get("metadata") or {}),
            )
            process_rows.append(process)
            stored_contract = raw.get("execution_contract")
            # Catalog Dockerfiles are the immutable executable authority. A stored
            # execution_contract may come from a legacy revision generated before
            # the catalog runtime contract was corrected, so never let it override
            # the current Dockerfile ENTRYPOINT/CMD.
            contract_options = runtime
            if stored_contract and not (catalog_managed and dockerfile_owns_entrypoint):
                contract_options = {**runtime, "execution_contract": stored_contract}
            execution_contracts[process.name] = RuntimeExecutionContract.from_runtime(
                process_name=process.name,
                process_command=process.command,
                process_entrypoint=process.entrypoint,
                runtime_options=contract_options,
                source_kind=source_kind,
                dockerfile=dockerfile,
            )

        endpoint_rows = []
        for raw in (getattr(revision, "endpoint_snapshot", None) or []):
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
        for key, item in (getattr(revision, "environment_snapshot", None) or {}).items():
            value = str(item.get("value") if isinstance(item, dict) else item)
            scope = str(item.get("scope") if isinstance(item, dict) else "runtime").lower()
            if scope in {"build", "both"}:
                build_environment[str(key)] = value
            if scope in {"runtime", "both"}:
                runtime_environment[str(key)] = value

        for process in process_rows:
            if not 1 <= process.replicas <= 8:
                raise ValueError(
                    f"Unsupported replica count {process.replicas!r} for process {process.name!r}; "
                    "PassDeployer supports between 1 and 8 replicas per process."
                )

        revision_id = getattr(revision, "pk", None)
        revision_number = getattr(revision, "revision_number", None)
        primary_contract = execution_contracts.get("web") or (
            next(iter(execution_contracts.values())) if execution_contracts else None
        )
        runtime_contract_hashes = {
            name: contract.contract_hash()
            for name, contract in execution_contracts.items()
        }
        return cls(
            source=source_snapshot,
            build=build_snapshot,
            runtime=runtime,
            build_environment=build_environment,
            runtime_environment=runtime_environment,
            environment=runtime_environment,
            processes=tuple(process_rows),
            endpoints=tuple(endpoint_rows),
            volumes=tuple(dict(v) for v in (getattr(revision, "volume_snapshot", None) or [])),
            networks=tuple(str(n) for n in (getattr(revision, "network_snapshot", None) or [])),
            metadata={
                "revision_id": str(revision_id or ""),
                "revision": revision_number,
                "source_kind": source_kind,
                "catalog_id": source_snapshot.get("catalog_id"),
                "variant_id": source_snapshot.get("variant_id"),
                "definition_version": source_snapshot.get("definition_version"),
                "runtime_contract_hashes": runtime_contract_hashes,
                "runtime_contract_hash": (
                    primary_contract.contract_hash()
                    if primary_contract is not None
                    else ""
                ),
            },
            execution_contracts=execution_contracts,
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
            docker_protocol = "udp" if endpoint.protocol == "udp" else "tcp"
            ports[f"{endpoint.target_port}/{docker_protocol}"] = {}
        return ports

    def port_bindings(self) -> dict[str, list[dict[str, str]]]:
        bindings: dict[str, list[dict[str, str]]] = {}
        for endpoint in self.enabled_endpoints():
            if endpoint.published_port is None:
                continue
            docker_protocol = "udp" if endpoint.protocol == "udp" else "tcp"
            key = f"{endpoint.target_port}/{docker_protocol}"
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
