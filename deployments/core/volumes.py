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

    def ensure_default_volumes(
        self,
        volumes: list[VolumeSpec],
        *,
        platform: str | None = None,
        service_name: str | None = None,
        size_mb: int | None = None,
    ) -> list[VolumeSpec]:
        """
        If the deploy has no volumes and the platform is known to need
        persistent storage, auto-create a named Docker volume.

        Does **not** require Django models — pure Docker volume creation
        via VolumeManager. On insufficient host space the volume is
        skipped (deploy continues with ephemeral storage) and a warning
        is logged.
        """
        if volumes:
            return list(volumes)

        p = (platform or "").lower().strip()
        if p not in self._DEFAULT_APP_VOLUME_TARGETS:
            return list(volumes)

        target, default_size = self._DEFAULT_APP_VOLUME_TARGETS[p]
        req_size = int(size_mb) if size_mb and size_mb > 0 else default_size

        # Derive a short Docker-legal name
        base = (service_name or "app").strip().lower()
        base = "".join(c if c.isalnum() else "-" for c in base).strip("-") or "app"
        vol_name = (base[:24] + "-data")[:32]

        ok, free_mb = Volume.check_host_space(req_size)
        if not ok:
            if self.logger:
                self.logger.warning(
                    "volume_creation",
                    f"Skipping auto-volume '{vol_name}': host has only "
                    f"{free_mb} MB free (need ~{req_size + 512} MB).",
                    progress=42,
                    details={"free_mb": free_mb, "requested_mb": req_size},
                )
            return list(volumes)

        try:
            Volume(
                name=vol_name,
                size_mb=req_size,
                driver="local",
            ).ensure()
        except VolumeError as exc:
            if self.logger:
                self.logger.warning(
                    "volume_creation",
                    f"Auto-volume creation failed (non-fatal): {exc}",
                    progress=42,
                    details={"volume": vol_name, "error": str(exc)},
                )
            return list(volumes)

        if self.logger:
            self.logger.info(
                "volume_creation",
                f"Auto-created default volume '{vol_name}' -> '{target}' "
                f"({req_size} MB) for platform '{p}'.",
                progress=42,
                details={
                    "volume": vol_name,
                    "target": target,
                    "size_mb": req_size,
                    "platform": p,
                },
            )

        return [
            VolumeSpec(
                source=vol_name,
                target=target,
                mode="rw",
                mount_type="volume",
                create=False,  # already ensured
                size_mb=req_size,
            )
        ]
