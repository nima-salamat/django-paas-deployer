
"""Typed deployment policy value objects.

These objects formalize build/runtime/exposure policy without becoming a
second mutable desired-state store. They serialize to the Mapping values
already used by DeploymentPlan for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class RolloutStrategy:
    kind: str = "RECREATE"
    batch_size: int = 1
    max_unavailable: int | None = None
    max_surge: int | None = None
    failure_policy: str = "rollback"
    progress_deadline: float | None = None
    minimum_ready: int = 1
    graceful_shutdown: float = 30.0

    def __post_init__(self) -> None:
        kind = str(self.kind).strip().upper()
        if kind not in {"ROLLING", "RECREATE", "CANARY", "BLUE_GREEN"}:
            raise ValueError(f"Unsupported rollout strategy {self.kind!r}")
        if int(self.batch_size) < 1:
            raise ValueError("rollout batch_size must be >= 1")
        if int(self.minimum_ready) < 0:
            raise ValueError("rollout minimum_ready must be >= 0")

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind).strip().upper(),
            "batch_size": int(self.batch_size),
            "max_unavailable": self.max_unavailable,
            "max_surge": self.max_surge,
            "failure_policy": str(self.failure_policy),
            "progress_deadline": self.progress_deadline,
            "minimum_ready": int(self.minimum_ready),
            "graceful_shutdown": float(self.graceful_shutdown),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "RolloutStrategy":
        raw = dict(value or {})
        return cls(**{key: raw[key] for key in cls.__dataclass_fields__ if key in raw})


@dataclass(frozen=True)
class HealthPolicy:
    readiness_required: bool = True
    source: str = "runtime"
    http_path: str | None = None
    expected_statuses: tuple[int, ...] = (200, 204)
    timeout: float = 60.0
    interval: float = 1.0
    startup_grace: float = 0.0
    failure_threshold: int = 3
    minimum_ready_duration: float = 0.0
    promotion_deadline: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "readiness_required": bool(self.readiness_required),
            "source": str(self.source),
            "http_path": self.http_path,
            "expected_statuses": list(self.expected_statuses),
            "timeout": float(self.timeout),
            "interval": float(self.interval),
            "startup_grace": float(self.startup_grace),
            "failure_threshold": int(self.failure_threshold),
            "minimum_ready_duration": float(self.minimum_ready_duration),
            "promotion_deadline": self.promotion_deadline,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "HealthPolicy":
        raw = dict(value or {})
        aliases = {
            "expected_status": "expected_statuses",
            "expected_statuses": "expected_statuses",
            "path": "http_path",
        }
        normalized = {}
        for key, item in raw.items():
            normalized[aliases.get(str(key), str(key))] = item
        if isinstance(normalized.get("expected_statuses"), int):
            normalized["expected_statuses"] = (normalized["expected_statuses"],)
        elif normalized.get("expected_statuses") is not None:
            normalized["expected_statuses"] = tuple(int(v) for v in normalized["expected_statuses"])
        return cls(**{key: normalized[key] for key in cls.__dataclass_fields__ if key in normalized})


@dataclass(frozen=True)
class ReleaseSpec:
    command: tuple[str, ...] = ()
    environment_references: tuple[str, ...] = ()
    timeout: float = 300.0
    failure_policy: str = "block"
    run_once: bool = True
    idempotency_key: str = ""
    execution_backend: str = "runtime"

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "environment_references": list(self.environment_references),
            "timeout": float(self.timeout),
            "failure_policy": str(self.failure_policy),
            "run_once": bool(self.run_once),
            "idempotency_key": str(self.idempotency_key),
            "execution_backend": str(self.execution_backend),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ReleaseSpec":
        raw = dict(value or {})
        command = raw.get("command", ())
        if isinstance(command, str):
            command = (command,)
        env = raw.get("environment_references", raw.get("environment_refs", ()))
        return cls(
            command=tuple(str(v) for v in command or ()),
            environment_references=tuple(str(v) for v in env or ()),
            timeout=float(raw.get("timeout", 300.0)),
            failure_policy=str(raw.get("failure_policy", "block")),
            run_once=bool(raw.get("run_once", True)),
            idempotency_key=str(raw.get("idempotency_key", "") or ""),
            execution_backend=str(raw.get("execution_backend", "runtime")),
        )


__all__ = ["RolloutStrategy", "HealthPolicy", "ReleaseSpec"]
