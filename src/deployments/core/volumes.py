"""
deployments/core/volumes.py
---------------------------
Volume mount preparation.

Key change vs. legacy:
  * Bind-mount ``source`` paths are now validated against an allow-list
    via ``security.validate_bind_source``.  The previous implementation
    interpolated ``volume.source`` straight into the Docker ``binds``
    config, which let a malicious user bind-mount ``/etc``,
    ``/var/run/docker.sock`` or any other host path into their container.
  * Named-volume sources are validated against the Docker name regex.
  * Duplicate-target detection is preserved.
"""

from __future__ import annotations

from deployments.common.exceptions import VolumeError
from deployments.common.security import (
    validate_bind_source,
    validate_docker_name,
)

from .manager.volume_manager import Volume
from deployments.core.types import VolumeSpec


MODE_MAP = {
    "ro": "ro",
    "readonly": "ro",
    "read": "ro",
    "rw": "rw",
    "readwrite": "rw",
    "write": "rw",
}


class VolumeMountManager:
    def __init__(self, logger=None):
        self.logger = logger

    def prepare(self, volumes: list[VolumeSpec], *, service_id: str | None = None) -> dict:
        """Ensure named volumes exist and return Docker bind mappings.

        A tenant deployment must refer to a registry-owned Volume row when a
        service_id is provided. This prevents Docker from creating persistent
        storage that is absent from Service quota accounting.
        """
        binds: dict[str, dict[str, str]] = {}
        targets: set[str] = set()

        for volume in volumes:
            target = volume.target
            if not target:
                raise VolumeError("Volume target is empty.", details={"source": volume.source})
            if target in targets:
                raise VolumeError(f"Duplicate volume target '{target}'.", details={"target": target})
            targets.add(target)

            mode = MODE_MAP.get((volume.mode or "rw").lower())
            if not mode:
                raise VolumeError(f"Unsupported volume mode '{volume.mode}'.", details={"source": volume.source, "target": target})

            mount_type = (volume.mount_type or "volume").lower()
            if mount_type == "volume":
                validate_docker_name(volume.source, field="volume_name")
                effective_size = volume.size_mb
                if service_id:
                    from services.models import Volume as RegistryVolume
                    registry_volume = None
                    for candidate in RegistryVolume.objects.filter(service_id=service_id):
                        if candidate.get_docker_volume_name() == volume.source:
                            registry_volume = candidate
                            break
                    if registry_volume is None:
                        raise VolumeError(
                            f"Managed Docker volume '{volume.source}' is not registered for this service; refusing unaccounted persistent storage.",
                            details={"volume": volume.source, "service_id": str(service_id), "capacity_mode": "LOGICAL_ONLY"},
                        )
                    effective_size = int(registry_volume.size_mb)
                    if volume.size_mb is not None and int(volume.size_mb) != effective_size:
                        raise VolumeError(
                            f"Declared volume capacity for '{volume.source}' does not match the registry allocation.",
                            details={
                                "volume": volume.source,
                                "service_id": str(service_id),
                                "registry_size_mb": effective_size,
                                "requested_size_mb": volume.size_mb,
                            },
                        )
                if volume.create:
                    if self.logger:
                        self.logger.info(
                            "volume_creation",
                            f"Ensuring Docker volume '{volume.source}' exists.",
                            progress=42,
                            details={
                                "volume": volume.source,
                                "target": target,
                                "declared_mb": effective_size,
                                "driver": volume.driver or "local",
                                "capacity_mode": "LOGICAL_ONLY" if (volume.driver or "local") == "local" else "UNKNOWN",
                            },
                        )
                    Volume(
                        name=volume.source,
                        size_mb=effective_size,
                        driver=volume.driver or "local",
                        driver_opts=dict(volume.driver_opts or {}),
                    ).ensure()
                binds[volume.source] = {"bind": target, "mode": mode}

            elif mount_type == "bind":
                safe_source = validate_bind_source(volume.source)
                if self.logger:
                    self.logger.info(
                        "volume_creation",
                        f"Using bind mount '{safe_source}' -> '{target}'.",
                        progress=42,
                        details={"source": safe_source, "target": target, "capacity_mode": "UNENFORCED"},
                    )
                binds[safe_source] = {"bind": target, "mode": mode}

            else:
                raise VolumeError(
                    f"Unsupported mount_type '{mount_type}'. Allowed: 'volume', 'bind'.",
                    details={"mount_type": mount_type, "source": volume.source},
                )

        return binds
    # Platforms that should receive a persistent data volume by default
    # when the caller did not supply any volumes.
    _DEFAULT_APP_VOLUME_TARGETS = {
        "laravel": ("/var/www/html/storage", 512),
        "php": ("/var/www/html/storage", 256),
        "django": ("/app/media", 512),
        "python": ("/app/data", 256),
        "flask": ("/app/data", 256),
        "nodejs": ("/app/data", 256),
        "nextjs": ("/app/data", 256),
    }

    def _docker_volume_exists(self, name: str) -> bool:
        try:
            Volume(name=name).client.volumes.get(name)
            return True
        except Exception:
            return False

    def ensure_default_volumes(
        self,
        volumes: list[VolumeSpec],
        *,
        platform: str | None = None,
        service_name: str | None = None,
        size_mb: int | None = None,
        service_id: str | None = None,
    ) -> list[VolumeSpec]:
        """Ensure platform-required persistent storage is registry-backed."""
        if volumes:
            return list(volumes)
        p = (platform or "").lower().strip()
        if p not in self._DEFAULT_APP_VOLUME_TARGETS:
            return list(volumes)
        if not service_id:
            raise VolumeError(
                f"Platform '{p}' requires managed persistent storage but no service identity was provided.",
                details={"platform": p, "capacity_mode": "UNKNOWN"},
            )
        from services.models import Service as RegistryService, Volume as RegistryVolume
        service = RegistryService.objects.select_related("plan").filter(pk=service_id).first()
        if service is None:
            raise VolumeError("Cannot provision a default persistent volume for a missing service.", details={"service_id": str(service_id), "platform": p})
        target, default_size = self._DEFAULT_APP_VOLUME_TARGETS[p]
        req_size = int(size_mb) if size_mb and size_mb > 0 else default_size
        existing = service.volumes.filter(default_bind=target).order_by("created_at").first()
        if existing is None:
            try:
                existing = RegistryVolume.objects.create(
                    name=(f"{''.join(c if c.isalnum() else '-' for c in (service_name or service.name).lower()).strip('-')[:24]}-data")[:32],
                    user=service.user,
                    service=service,
                    service_attachments={str(service.pk): {"bind": target, "mode": "rw"}},
                    default_bind=target,
                    default_mode="rw",
                    size_mb=req_size,
                )
            except Exception as exc:
                raise VolumeError(
                    f"Failed to register required persistent volume for service '{service.name}'.",
                    details={
                        "service_id": str(service.pk),
                        "requested_mb": req_size,
                        "exception_type": type(exc).__name__,
                        "technical_message": str(exc),
                    },
                ) from exc
        docker_name = existing.get_docker_volume_name()
        spec = VolumeSpec(
            source=docker_name,
            target=target,
            mode=existing.default_mode or "rw",
            mount_type="volume",
            driver="local",
            create=not self._docker_volume_exists(docker_name),
            size_mb=int(existing.size_mb),
        )
        return [spec]

