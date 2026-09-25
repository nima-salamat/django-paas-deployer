"""Safe, explainable metadata for effective deployment configuration."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Mapping


SENSITIVE_KEY_RE = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|authorization|credential)",
    re.IGNORECASE,
)
REDACTED = "[REDACTED]"


def is_sensitive_key(key: str) -> bool:
    return bool(SENSITIVE_KEY_RE.search(str(key)))


def redact_value(value: Any, *, key: str = "") -> Any:
    """Return a JSON-like copy with sensitive values removed."""

    if is_sensitive_key(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_value(item, key=key) for item in value]
    return copy.deepcopy(value)


@dataclass(frozen=True)
class ProvenanceRecord:
    path: str
    source: str
    effective: Any
    requested: Any = None
    constrained_by: tuple[str, ...] = ()
    redacted: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "effective": redact_value(self.effective, key=self.path),
            "requested": redact_value(self.requested, key=self.path),
            "constrained_by": list(self.constrained_by),
            "redacted": self.redacted or is_sensitive_key(self.path),
        }


@dataclass
class ConfigurationProvenance:
    """Mutable builder used while resolving one immutable configuration."""

    records: dict[str, ProvenanceRecord] = field(default_factory=dict)
    rejected: list[dict[str, Any]] = field(default_factory=list)

    def record(
        self,
        path: str,
        *,
        source: str,
        effective: Any,
        requested: Any = None,
        constrained_by: tuple[str, ...] = (),
    ) -> None:
        self.records[path] = ProvenanceRecord(
            path=path,
            source=source,
            effective=copy.deepcopy(effective),
            requested=copy.deepcopy(requested),
            constrained_by=tuple(constrained_by),
            redacted=is_sensitive_key(path),
        )

    def reject(self, path: str, *, source: str, reason: str) -> None:
        self.rejected.append({"path": path, "source": source, "reason": reason})

    def explain(self, path: str) -> dict[str, Any] | None:
        record = self.records.get(path)
        return record.as_dict() if record else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "values": {path: record.as_dict() for path, record in sorted(self.records.items())},
            "rejected": copy.deepcopy(self.rejected),
        }
