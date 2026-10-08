"""Canonical, non-secret runtime execution contract helpers.

The contract describes Docker executable semantics without exposing Docker SDK
objects or tenant secrets. It is the single source of truth for the transition
from the immutable Runtime Graph through plan compilation to Swarm ContainerSpec.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from datetime import datetime, timezone
import hashlib
import json
import os
import shlex
import socket
from typing import Any, Mapping


RUNTIME_CONTRACT_VERSION = "1"
ENTRYPOINT_SOURCES = frozenset({"IMAGE", "PLATFORM", "USER"})
_WORKER_STARTED_AT = datetime.now(timezone.utc)


def _tokens(value: Any) -> tuple[str, ...]:
    if value in (None, "", []):
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return tuple(shlex.split(str(value)))


def _command_tokens(value: Any) -> tuple[str, ...]:
    if value in (None, "", []):
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ("/bin/sh", "-lc", str(value))


def _dockerfile_instruction(dockerfile: str, instruction: str) -> tuple[str, ...]:
    matches = list(
        re.finditer(
            rf"^\s*{instruction}\s+(.+)$",
            dockerfile or "",
            flags=re.MULTILINE | re.IGNORECASE,
        )
    )
    if not matches:
        return ()
    raw = matches[-1].group(1).strip()
    if raw.startswith("["):
        try:
            values = json.loads(raw)
        except (TypeError, ValueError):
            return ()
        if isinstance(values, list) and all(isinstance(item, str) for item in values):
            return tuple(values)
        return ()
    # Dockerfile shell-form ENTRYPOINT/CMD semantics are represented by the
    # shell explicitly instead of pretending the raw string is argv[0].
    return ("/bin/sh", "-c", raw)


def dockerfile_has_instruction(dockerfile: str, instruction: str) -> bool:
    return bool(_dockerfile_instruction(dockerfile, instruction))


@dataclass(frozen=True)
class RuntimeExecutionContract:
    entrypoint_source: str = "PLATFORM"
    image_entrypoint: tuple[str, ...] = ()
    image_cmd: tuple[str, ...] = ()
    command: tuple[str, ...] | None = None
    args: tuple[str, ...] = ()
    catalog_managed: bool = False
    image_entrypoint_owned: bool = False
    process_name: str = "web"
    contract_version: str = RUNTIME_CONTRACT_VERSION
    required_executables: tuple[str, ...] = ()
    source_kind: str = ""

    def __post_init__(self) -> None:
        source = str(self.entrypoint_source or "PLATFORM").upper()
        if source not in ENTRYPOINT_SOURCES:
            raise ValueError(f"Unsupported runtime entrypoint source: {source!r}")
        object.__setattr__(self, "entrypoint_source", source)
        object.__setattr__(self, "image_entrypoint", tuple(self.image_entrypoint or ()))
        object.__setattr__(self, "image_cmd", tuple(self.image_cmd or ()))
        object.__setattr__(self, "command", None if self.command is None else tuple(self.command))
        object.__setattr__(self, "args", tuple(self.args or ()))
        object.__setattr__(self, "required_executables", tuple(self.required_executables or ()))
        object.__setattr__(self, "process_name", str(self.process_name or "web"))
        object.__setattr__(self, "source_kind", str(self.source_kind or "").lower())

    @classmethod
    def from_runtime(
        cls,
        *,
        process_name: str = "web",
        process_command: Any = None,
        process_entrypoint: Any = None,
        runtime_options: Mapping[str, Any] | None = None,
        source_kind: str = "",
        dockerfile: str = "",
    ) -> "RuntimeExecutionContract":
        options = dict(runtime_options or {})
        stored = options.get("execution_contract")
        if isinstance(stored, RuntimeExecutionContract):
            return stored
        if isinstance(stored, Mapping):
            return cls.from_dict(stored)

        catalog_managed = bool(options.get("catalog_managed"))
        image_owned = bool(options.get("image_entrypoint_owned"))
        dockerfile_entrypoint = _dockerfile_instruction(dockerfile, "ENTRYPOINT")
        image_entrypoint_owned = bool(
            image_owned or (catalog_managed and dockerfile_entrypoint)
        )
        image_cmd = _dockerfile_instruction(dockerfile, "CMD")

        if image_entrypoint_owned:
            source = "IMAGE"
            command = None
            args = _tokens(process_command) or image_cmd
        else:
            source = "USER" if process_entrypoint not in (None, "", []) else "PLATFORM"
            command = _command_tokens(process_entrypoint) or _command_tokens(process_command) or None
            args = ()

        required: list[str] = []
        # Only image-owned absolute application commands are safe to preflight
        # generically. Platform/user shell-wrapped commands may intentionally
        # resolve an executable from PATH and must preserve existing semantics.
        if image_entrypoint_owned:
            executable = args[0] if args else ""
            if executable.startswith("/"):
                required.append(executable)

        return cls(
            entrypoint_source=source,
            image_entrypoint=dockerfile_entrypoint,
            image_cmd=image_cmd,
            command=command,
            args=args,
            catalog_managed=bool(catalog_managed),
            image_entrypoint_owned=image_entrypoint_owned,
            process_name=process_name,
            required_executables=tuple(dict.fromkeys(required)),
            source_kind=source_kind,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RuntimeExecutionContract":
        data = dict(value)
        return cls(
            entrypoint_source=str(data.get("entrypoint_source") or "PLATFORM"),
            image_entrypoint=_tokens(data.get("image_entrypoint")),
            image_cmd=_tokens(data.get("image_cmd")),
            command=None if data.get("command") is None else _tokens(data.get("command")),
            args=_tokens(data.get("args")),
            catalog_managed=bool(data.get("catalog_managed")),
            image_entrypoint_owned=bool(data.get("image_entrypoint_owned")),
            process_name=str(data.get("process_name") or "web"),
            contract_version=str(data.get("contract_version") or RUNTIME_CONTRACT_VERSION),
            required_executables=_tokens(data.get("required_executables")),
            source_kind=str(data.get("source_kind") or ""),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "entrypoint_source": self.entrypoint_source,
            "image_entrypoint": list(self.image_entrypoint),
            "image_cmd": list(self.image_cmd),
            "command": list(self.command) if self.command is not None else None,
            "args": list(self.args),
            "catalog_managed": self.catalog_managed,
            "image_entrypoint_owned": self.image_entrypoint_owned,
            "process_name": self.process_name,
            "contract_version": self.contract_version,
            "required_executables": list(self.required_executables),
            "source_kind": self.source_kind,
        }

    def contract_hash(self) -> str:
        """Stable hash of the non-secret runtime execution contract itself."""
        encoded = json.dumps(
            self.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def fingerprint(self, *, boundary: str = "", image_ref: str = "", artifact_digest: str = "") -> str:
        """Contextual fingerprint for diagnostics; contract_hash is the drift key."""
        payload = self.as_dict()
        if boundary:
            payload["boundary"] = boundary
        if image_ref:
            payload["image_ref"] = str(image_ref)
        if artifact_digest:
            payload["artifact_digest"] = str(artifact_digest)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def expected_swarm_spec(self) -> dict[str, Any]:
        if self.entrypoint_source == "IMAGE":
            return {
                "Command": None,
                "Args": list(self.args),
                "Entrypoint": None,
            }
        return {
            "Command": list(self.command) if self.command is not None else None,
            "Args": list(self.args) if self.args else None,
            "Entrypoint": None,
        }


def validate_swarm_contract(
    contract: RuntimeExecutionContract,
    *,
    service_doc: Mapping[str, Any],
    boundary: str = "swarm_container_spec",
) -> dict[str, Any]:
    """Validate the compiled Stack-shaped service before Docker mutation."""
    actual_entrypoint = service_doc.get("entrypoint")
    actual_command = service_doc.get("command")
    actual_args = service_doc.get("args")
    expected = contract.expected_swarm_spec()
    actual_effective_command = (
        actual_entrypoint if actual_entrypoint not in (None, "", []) else actual_command
    )
    expected_command = tuple(expected["Command"] or ())
    expected_args = tuple(expected["Args"] or ())
    actual_command_tokens = _tokens(actual_effective_command)
    actual_args_tokens = _tokens(actual_args)
    actual_payload = {
        "entrypoint_source": contract.entrypoint_source,
        "image_entrypoint": list(contract.image_entrypoint),
        "image_cmd": list(contract.image_cmd),
        "command": list(actual_command_tokens) if actual_command_tokens else None,
        "args": list(actual_args_tokens),
        "catalog_managed": contract.catalog_managed,
        "image_entrypoint_owned": contract.image_entrypoint_owned,
        "process_name": contract.process_name,
        "contract_version": contract.contract_version,
    }
    actual_encoded = json.dumps(actual_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    actual_contract_hash = hashlib.sha256(actual_encoded.encode("utf-8")).hexdigest()
    mismatch = (
        contract.entrypoint_source == "IMAGE"
        and actual_entrypoint not in (None, "", [])
    )
    mismatch = mismatch or actual_command_tokens != expected_command
    mismatch = mismatch or actual_args_tokens != expected_args

    return {
        "valid": not mismatch,
        "boundary": boundary,
        "expected": expected,
        "actual": {
            "entrypoint": actual_entrypoint,
            "command": actual_command,
            "args": actual_args,
            "effective_command": actual_effective_command,
        },
        "revision_contract_hash": contract.contract_hash(),
        "compiled_swarm_contract_hash": contract.contract_hash(),
        "expected_contract_hash": contract.contract_hash(),
        "actual_contract_hash": actual_contract_hash,
    }


def worker_provenance() -> dict[str, str]:
    revision = (
        os.environ.get("PASSDEPLOYER_GIT_SHA")
        or os.environ.get("GIT_COMMIT_SHA")
        or os.environ.get("BUILD_GIT_SHA")
        or os.environ.get("GIT_SHA")
        or "unknown"
    )
    started = _WORKER_STARTED_AT.isoformat()
    return {
        "worker_code_revision": str(revision),
        "worker_started_at": started,
        "worker_instance_id": f"{socket.gethostname()}:{os.getpid()}",
    }


__all__ = [
    "ENTRYPOINT_SOURCES",
    "RUNTIME_CONTRACT_VERSION",
    "RuntimeExecutionContract",
    "dockerfile_has_instruction",
    "validate_swarm_contract",
    "worker_provenance",
]
