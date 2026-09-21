import os
import re

from .exceptions import DeploymentValidationError
from .types import DeploymentConfig, VolumeSpec


# Docker repository names MUST be lowercase
DOCKER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]+$")
IMAGE_TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")
VOLUME_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]+$")
ABSOLUTE_CONTAINER_PATH_RE = re.compile(r"^/[^:\0]*$")


class DeploymentValidator:
    def validate(self, config: DeploymentConfig) -> None:
        errors = []

        if not config.name or not DOCKER_NAME_RE.match(str(config.name)):
            errors.append(
                "Container/image name must use only lowercase letters, numbers, "
                "dot, underscore, or dash (Docker requires lowercase)."
            )

        tag = str(config.tag) if config.tag is not None else ""
        if not tag or not IMAGE_TAG_RE.match(tag):
            errors.append(
                f"Image tag is missing or invalid: {config.tag!r}. "
                "Use alphanumeric tags (e.g. v1-22)."
            )

        if not config.zip_path or not os.path.exists(config.zip_path):
            errors.append(
                f"Deployment ZIP file does not exist: {config.zip_path!r}"
            )

        if not config.dockerfile_template:
            errors.append("Dockerfile template is missing for this platform.")

        if config.max_cpu is None or float(config.max_cpu) <= 0:
            errors.append("CPU limit must be greater than zero.")

        if config.max_ram is None or int(config.max_ram) <= 0:
            errors.append("RAM limit must be greater than zero.")

        if config.port is not None and (
            int(config.port) <= 0 or int(config.port) > 65535
        ):
            errors.append("Container port must be between 1 and 65535.")

        if not config.networks:
            errors.append("At least one Docker network is required.")
        else:
            for network in config.networks:
                if not network.name or not DOCKER_NAME_RE.match(network.name):
                    errors.append(
                        f"Network name '{network.name}' is invalid "
                        "(must be lowercase)."
                    )

        for volume in config.volumes:
            errors.extend(self._validate_volume(volume))

        if errors:
            raise DeploymentValidationError(
                "Deployment validation failed.",
                details={"errors": errors},
            )

    def _validate_volume(self, volume: VolumeSpec) -> list[str]:
        errors = []
        mount_type = (volume.mount_type or "").lower()
        mode = (volume.mode or "").lower()

        if mount_type not in {"volume", "bind"}:
            errors.append(
                f"Volume mount type for target '{volume.target}' must be "
                "'volume' or 'bind'."
            )

        if mode not in {
            "ro", "rw", "read", "write", "readwrite", "readonly",
        }:
            errors.append(
                f"Volume mode for target '{volume.target}' must be "
                "read-only or read-write."
            )

        if not volume.target or not ABSOLUTE_CONTAINER_PATH_RE.match(volume.target):
            errors.append(
                f"Volume target '{volume.target}' must be an absolute "
                "container path."
            )

        if mount_type == "volume":
            if not volume.source or not VOLUME_NAME_RE.match(volume.source):
                errors.append(
                    f"Docker volume name '{volume.source}' is invalid."
                )
            if volume.size_mb is not None and int(volume.size_mb) <= 0:
                errors.append(
                    f"Docker volume '{volume.source}' size must be "
                    "greater than zero."
                )

        if mount_type == "bind":
            if not volume.source or not os.path.isabs(volume.source):
                errors.append(
                    f"Bind mount source for target '{volume.target}' must "
                    "be an absolute host path."
                )
            elif not os.path.exists(volume.source):
                errors.append(
                    f"Bind mount source '{volume.source}' does not exist."
                )

        return errors
