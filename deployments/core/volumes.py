from .exceptions import VolumeError
from .manager.volume_manager import Volume
from .types import VolumeSpec


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
        binds = {}
        targets = set()

        for volume in volumes:
            target = volume.target
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
            if mount_type == "volume" and volume.create:
                if self.logger:
                    self.logger.info(
                        "volume_creation",
                        f"Ensuring Docker volume '{volume.source}' exists.",
                        progress=42,
                        details={"volume": volume.source, "target": target},
                    )
                Volume(
                    name=volume.source,
                    size_mb=volume.size_mb,
                    driver=volume.driver,
                    driver_opts=volume.driver_opts,
                ).ensure()
            elif mount_type == "bind" and self.logger:
                self.logger.info(
                    "volume_creation",
                    f"Using bind mount '{volume.source}' -> '{target}'.",
                    progress=42,
                    details={"source": volume.source, "target": target},
                )

            binds[volume.source] = {"bind": target, "mode": mode}

        return binds
