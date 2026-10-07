"""Central Docker resource identity and naming policy for PassDeployer.

This module is deliberately dependency-light: it does not import Django or
Docker. Every subsystem that creates, resolves, or validates a PassDeployer-
owned Docker identifier should use these functions instead of inventing its
own formatting rules.

Canonical identities:
  service/container: app-<service-id8>-<service-name>
  network:            net-<network-id8>-<network-name>
  volume:             vol-<volume-id8>-<volume-name>
  application image:  <service/container-name>:<deploy-version>
  process container:  <service-name>-<process>-<replica>-<deployment-suffix>

Historical service names are exposed only as lookup candidates for cleanup
and reconciliation. New resources are never created with a legacy identity.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from .exceptions import DeploymentSecurityError


_DOCKER_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_DOCKER_REPOSITORY_RE = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*$"
)
_IMAGE_TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")


def _text(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _raw(value: Any) -> str:
    return str(value if value is not None else "")


def _uuid8(value: Any, *, field: str) -> str:
    raw = _text(getattr(value, "hex", value)).replace("-", "").lower()
    if len(raw) < 8 or not re.fullmatch(r"[0-9a-f]{8,}", raw):
        raise DeploymentSecurityError(
            f"Invalid {field}: a UUID-like identifier is required.",
            stage="identity_validation",
            code="DOCKER_IDENTITY_INVALID_OWNER_ID",
            user_message="The platform could not derive a valid Docker resource identity.",
            details={"field": field},
        )
    return raw[:8]


def validate_docker_component(value: Any, *, field: str, max_length: int = 256) -> str:
    """Validate one Docker name component without rewriting it."""
    cleaned = _raw(value)
    if not cleaned:
        raise DeploymentSecurityError(
            f"Invalid {field}: value is empty.",
            stage="identity_validation",
            code="DOCKER_IDENTITY_EMPTY",
            user_message=f"The generated Docker {field.replace('_', ' ')} is empty.",
            details={"field": field},
        )
    if len(cleaned) > max_length:
        raise DeploymentSecurityError(
            f"Invalid {field}: value is longer than {max_length} characters.",
            stage="identity_validation",
            code="DOCKER_IDENTITY_TOO_LONG",
            user_message=f"The generated Docker {field.replace('_', ' ')} is too long.",
            details={"field": field, "max_length": max_length},
        )
    if not _DOCKER_COMPONENT_RE.fullmatch(cleaned):
        raise DeploymentSecurityError(
            f"Invalid {field}: {cleaned!r} contains characters that Docker does not allow.",
            stage="identity_validation",
            code="DOCKER_IDENTITY_INVALID_COMPONENT",
            user_message=(
                f"The generated Docker {field.replace('_', ' ')} is invalid. "
                "Use letters, numbers, '.', '_' or '-'."
            ),
            details={"field": field, "value": cleaned},
        )
    return cleaned


def validate_image_repository(value: Any) -> str:
    """Validate a lowercase Docker repository path, including namespaces."""
    cleaned = _raw(value)
    if not cleaned:
        raise DeploymentSecurityError(
            "Image repository is empty.",
            stage="identity_validation",
            code="DOCKER_IMAGE_REPOSITORY_EMPTY",
            user_message="The deployment generated an empty Docker image repository.",
        )
    if cleaned != cleaned.lower() or len(cleaned) > 255 or not _DOCKER_REPOSITORY_RE.fullmatch(cleaned):
        raise DeploymentSecurityError(
            f"Invalid Docker image repository: {value!r}",
            stage="identity_validation",
            code="DOCKER_IMAGE_REPOSITORY_INVALID",
            user_message="The deployment generated an invalid Docker image repository.",
            details={"repository": cleaned},
        )
    return cleaned


def canonical_image_tag(value: Any, *, default: str = "latest") -> str:
    """Return the exact model-provided tag after validation.

    Decimal deployment versions such as Decimal('1.00') intentionally remain
    '1.00'. No synthetic prefix/suffix is added.
    """
    cleaned = _text(value) or default
    if len(cleaned) > 128 or not _IMAGE_TAG_RE.fullmatch(cleaned):
        raise DeploymentSecurityError(
            f"Invalid Docker image tag: {value!r}",
            stage="identity_validation",
            code="DOCKER_IMAGE_TAG_INVALID",
            user_message=(
                "The deployment version cannot be used as a Docker image tag. "
                "Choose a version containing only letters, numbers, '.', '_' or '-'."
            ),
            details={"tag": cleaned},
        )
    return cleaned


def canonical_image_ref(repository: Any, tag: Any = None) -> str:
    """Build one canonical repository:tag reference."""
    repo = validate_image_repository(repository)
    return f"{repo}:{canonical_image_tag(tag)}"


def canonical_service_name(service_id: Any, service_name: Any) -> str:
    """Canonical container/repository identity for a Service."""
    sid = _uuid8(service_id, field="service_id")
    raw_name = _raw(service_name).lower()
    if not raw_name:
        raise DeploymentSecurityError(
            "Service name is empty.",
            stage="identity_validation",
            code="DOCKER_SERVICE_NAME_EMPTY",
            user_message="The service does not have a valid Docker identity.",
        )
    # Preserve the existing naming contract exactly; validate rather than
    # silently changing a persisted Service.name into a different identity.
    return validate_docker_component(
        f"app-{sid}-{raw_name}",
        field="service_name",
        max_length=63,
    )


def legacy_service_name_candidates(service_id: Any, service_name: Any) -> tuple[str, ...]:
    """Return canonical + historical service/container names for lookup only."""
    sid = _uuid8(service_id, field="service_id")
    raw_name = _raw(service_name).lower()
    canonical = canonical_service_name(sid, raw_name)
    # These are historical names used by the project before the current
    # app-<id8>-<name> contract was stabilized.
    candidates = (
        canonical,
        f"{sid}-{raw_name}",
        f"local/{sid}-{raw_name}",
    )
    return tuple(dict.fromkeys(candidates))


def canonical_network_name(network_id: Any, network_name: Any) -> str:
    nid = _uuid8(network_id, field="network_id")
    return validate_docker_component(
        f"net-{nid}-{_raw(network_name)}",
        field="network_name",
        max_length=63,
    )


def canonical_volume_name(volume_id: Any, volume_name: Any) -> str:
    vid = _uuid8(volume_id, field="volume_id")
    return validate_docker_component(
        f"vol-{vid}-{_raw(volume_name)}",
        field="volume_name",
        max_length=63,
    )


def canonical_runtime_process_service_name(service_name: Any, process_name: Any) -> str:
    """Canonical Swarm service identity for a non-web process."""
    base = canonical_swarm_service_name(service_name)
    process = _raw(process_name).strip().lower()
    if not process:
        raise DeploymentSecurityError(
            "Process name is empty.",
            stage="identity_validation",
            code="DOCKER_PROCESS_NAME_EMPTY",
            user_message="The deployment generated an empty process name.",
        )
    process = validate_docker_component(
        process,
        field="process_name",
        max_length=32,
    )
    return validate_docker_component(
        f"{base}-{process}",
        field="swarm_process_service_name",
        max_length=63,
    )


def canonical_process_name(
    service_name: Any,
    process_name: Any,
    replica: int,
    deployment_id: Any,
) -> str:
    base = validate_docker_component(
        service_name,
        field="service_name",
        max_length=63,
    )
    process = re.sub(r"[^a-z0-9-]+", "-", _text(process_name).lower()).strip("-") or "process"
    process = validate_docker_component(process, field="process_name", max_length=32)
    try:
        replica_value = int(replica)
    except (TypeError, ValueError) as exc:
        raise DeploymentSecurityError(
            "Process replica must be an integer.",
            stage="identity_validation",
            code="DOCKER_PROCESS_REPLICA_INVALID",
        ) from exc
    if replica_value < 1:
        raise DeploymentSecurityError(
            "Process replica must be at least 1.",
            stage="identity_validation",
            code="DOCKER_PROCESS_REPLICA_INVALID",
        )
    deployment = re.sub(
        r"[^a-z0-9-]+",
        "-",
        _text(deployment_id).lower(),
    ).strip("-")
    deployment = deployment[-12:] or "current"
    return validate_docker_component(
        f"{base}-{process}-{replica_value}-{deployment}",
        field="process_container_name",
        max_length=255,
    )


def canonical_swarm_service_name(service_name: Any) -> str:
    """Swarm service names use the same canonical runtime identity."""
    return validate_docker_component(
        _text(service_name).lower(),
        field="swarm_service_name",
        max_length=63,
    )


def canonical_remote_image_ref(
    service_name: Any,
    tag: Any,
    *,
    registry: Any = "",
    namespace: Any = "",
) -> str:
    """Build the registry-qualified image ref used by Swarm when configured."""
    service = canonical_swarm_service_name(service_name)
    clean_registry = _raw(registry).strip().rstrip("/")
    clean_namespace = _raw(namespace).strip("/")
    if clean_registry:
        if not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]{1,5})?", clean_registry):
            raise DeploymentSecurityError(
                f"Invalid Docker registry endpoint: {registry!r}",
                stage="identity_validation",
                code="DOCKER_REGISTRY_INVALID",
                user_message="The configured Docker image registry is invalid.",
            )
        if clean_namespace:
            namespace_repo = f"{clean_registry.lower()}/{clean_namespace.lower()}/{service}"
        else:
            namespace_repo = f"{clean_registry.lower()}/{service}"
        # Validate the repository after removing the optional registry
        # endpoint syntax. Registry host/port is valid Docker syntax but is
        # intentionally outside repository-name validation.
        if not re.fullmatch(
            r"(?:[a-z0-9.-]+(?::[0-9]{1,5})?/)?"
            r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*",
            namespace_repo,
        ):
            raise DeploymentSecurityError(
                f"Invalid Docker remote image repository: {namespace_repo!r}",
                stage="identity_validation",
                code="DOCKER_REMOTE_IMAGE_REPOSITORY_INVALID",
                user_message="The deployment generated an invalid Docker registry image reference.",
                details={"repository": namespace_repo},
            )
        repo = namespace_repo
    return f"{repo}:{canonical_image_tag(tag)}"


def candidate_image_refs(service_id: Any, service_name: Any, tag: Any) -> tuple[str, ...]:
    """Return canonical + legacy application image refs for discovery/cleanup."""
    validated_tag = canonical_image_tag(tag)
    return tuple(
        f"{name}:{validated_tag}"
        for name in legacy_service_name_candidates(service_id, service_name)
        if "/" not in name
        or name.startswith("local/")
    )


__all__ = [
    "canonical_image_ref",
    "canonical_image_tag",
    "canonical_service_name",
    "canonical_network_name",
    "canonical_volume_name",
    "canonical_process_name",
    "canonical_runtime_process_service_name",
    "canonical_swarm_service_name",
    "canonical_remote_image_ref",
    "candidate_image_refs",
    "legacy_service_name_candidates",
    "validate_docker_component",
    "validate_image_repository",
]
