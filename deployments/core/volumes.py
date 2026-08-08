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

    def prepare(self, volumes: list[VolumeSpec]) -> dict:
        """
        Ensure named volumes exist and return a docker-py ``binds`` dict.

        ``size_mb`` on VolumeSpec is application quota metadata only. It is
        forwarded to ``Volume()`` for drivers that support size limits;
        the stock ``local`` driver ignores it (see volume_manager.Volume._options).
        """
        binds: dict[str, dict[str, str]] = {}
        targets: set[str] = set()

        for volume in volumes:
            target = volume.target
            if not target:
                raise VolumeError(
                    "Volume target is empty.",
                    details={"source": volume.source},
                )
            if target in targets:
                raise VolumeError(
                    f"Duplicate volume target '{target}'.",
                    details={"target": target},
                )
            targets.add(target)

            mode = MODE_MAP.get((volume.mode or "rw").lower())
            if not mode:
                raise VolumeError(
                    f"Unsupported volume mode '{volume.mode}'.",
                    details={"source": volume.source, "target": target},
                )

            mount_type = (volume.mount_type or "volume").lower()

            if mount_type == "volume":
                # Named Docker volume — name must be a valid Docker identifier.
                validate_docker_name(volume.source, field="volume_name")
                if volume.create:
                    if self.logger:
                        self.logger.info(
                            "volume_creation",
                            f"Ensuring Docker volume '{volume.source}' exists.",
                            progress=42,
                            details={
                                "volume": volume.source,
                                "target": target,
                                "size_mb": volume.size_mb,
                                "driver": volume.driver or "local",
                            },
                        )
                    Volume(
                        name=volume.source,
                        size_mb=volume.size_mb,
                        driver=volume.driver or "local",
                        driver_opts=dict(volume.driver_opts or {}),
                    ).ensure()
                binds[volume.source] = {"bind": target, "mode": mode}

            elif mount_type == "bind":
                # Bind mount — source MUST be inside an allowed prefix.
                # This is the critical security check that was missing.
                safe_source = validate_bind_source(volume.source)
                if self.logger:
                    self.logger.info(
                        "volume_creation",
                        f"Using bind mount '{safe_source}' -> '{target}'.",
                        progress=42,
                        details={"source": safe_source, "target": target},
                    )
                binds[safe_source] = {"bind": target, "mode": mode}

            else:
                raise VolumeError(
                    f"Unsupported mount_type '{mount_type}'. "
                    f"Allowed: 'volume', 'bind'.",
                    details={"mount_type": mount_type, "source": volume.source},
                )

        return binds
