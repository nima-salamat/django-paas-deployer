
"""Runtime-neutral immutable artifact reference and publication contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class ArtifactReference:
    digest: str
    image_ref: str
    source_digest: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ArtifactRegistry(Protocol):
    """Runtime-independent artifact availability boundary."""

    def publish(
        self,
        artifact: ArtifactReference,
        *,
        service_name: str,
        tag: str,
        operation_key: str,
    ) -> ArtifactReference:
        ...

    def resolve(self, digest: str) -> ArtifactReference | None:
        ...

    def ensure_available(
        self,
        artifact: ArtifactReference,
        *,
        service_name: str,
        tag: str,
        operation_key: str,
    ) -> ArtifactReference:
        ...

    def pull(self, digest: str, *, operation_key: str) -> ArtifactReference:
        ...

    def metadata(self, digest: str) -> Mapping[str, Any]:
        ...


class SwarmArtifactRegistry:
    """Adapt existing Swarm image publication without leaking Docker into plans."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def publish(
        self,
        artifact: ArtifactReference,
        *,
        service_name: str,
        tag: str,
        operation_key: str,
    ) -> ArtifactReference:
        image_ref = self.runtime.prepare_image(
            artifact.image_ref,
            service_name,
            tag,
        )
        return ArtifactReference(
            digest=artifact.digest,
            image_ref=str(image_ref),
            source_digest=artifact.source_digest,
            metadata={**dict(artifact.metadata), "operation_key": operation_key},
        )

    def resolve(self, digest: str) -> ArtifactReference | None:
        # SwarmRuntime owns the concrete Docker/registry lookup. There is no
        # authoritative remote-only registry resolver yet, so unknown remains
        # explicit instead of pretending a digest is portable.
        return None

    def ensure_available(
        self,
        artifact: ArtifactReference,
        *,
        service_name: str,
        tag: str,
        operation_key: str,
    ) -> ArtifactReference:
        registry = str(__import__("os").environ.get("SWARM_IMAGE_REGISTRY") or "").strip().rstrip("/")
        image_ref = str(artifact.image_ref or "")
        if registry and image_ref.startswith(registry + "/"):
            return artifact
        return self.publish(
            artifact,
            service_name=service_name,
            tag=tag,
            operation_key=operation_key,
        )

    def pull(self, digest: str, *, operation_key: str) -> ArtifactReference:
        raise RuntimeError(
            f"Swarm artifact pull by digest is not implemented for {digest!r}; "
            "configure an artifact registry before requiring remote-only pulls."
        )

    def metadata(self, digest: str) -> Mapping[str, Any]:
        return {"digest": str(digest), "registry_lookup": "unsupported"}
