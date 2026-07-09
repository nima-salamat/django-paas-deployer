import logging

import docker

from .client_manager import Client
from deployments.core.exceptions import VolumeError

logger = logging.getLogger(__name__)


class Volume(Client):
    def __init__(self, name: str, size_mb: int = None, driver: str = "local", driver_opts: dict = None):
        super().__init__()
        self.name = name
        self.driver = driver or "local"
        self.size_mb = size_mb
        self.driver_opts = driver_opts or {}

    def _options(self):
        opts = dict(self.driver_opts)
        if self.size_mb:
            opts.setdefault("size", f"{self.size_mb}Mb")
        return opts

    def create(self):
        try:
            volume = self.client.volumes.create(
                name=self.name,
                driver=self.driver,
                driver_opts=self._options(),
                labels={"managed-by": "django-paas-deployer"},
            )
            logger.info("Volume '%s' created with driver '%s'", self.name, self.driver)
            return volume
        except docker.errors.APIError as exc:
            if getattr(exc, "status_code", None) == 409 or "already exists" in str(exc):
                return self.client.volumes.get(self.name)
            raise VolumeError(
                f"Failed to create Docker volume '{self.name}'.",
                details={"volume": self.name, "driver": self.driver},
            ) from exc
        except docker.errors.DockerException as exc:
            raise VolumeError(
                f"Failed to create Docker volume '{self.name}'.",
                details={"volume": self.name, "driver": self.driver},
            ) from exc

    def ensure(self):
        try:
            return self.client.volumes.get(self.name)
        except docker.errors.NotFound:
            return self.create()
        except docker.errors.DockerException as exc:
            raise VolumeError(
                f"Failed to inspect Docker volume '{self.name}'.",
                details={"volume": self.name},
            ) from exc

    def remove(self):
        try:
            volume = self.client.volumes.get(self.name)
        except docker.errors.NotFound:
            logger.info("Volume '%s' not found; nothing to remove.", self.name)
            return True

        try:
            volume.remove()
            logger.info("Volume '%s' deleted.", self.name)
            return True
        except docker.errors.DockerException as exc:
            raise VolumeError(f"Failed to remove Docker volume '{self.name}'.") from exc
