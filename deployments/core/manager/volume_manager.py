import logging

import docker

from .client_manager import Client
from deployments.core.exceptions import VolumeError

logger = logging.getLogger(__name__)


# Drivers known to honour a size-like option. The stock "local" driver does
# NOT support "size" — passing it causes APIError and aborts the deploy.
# size_mb on the Django Volume model is only for application-level quota.
_SIZE_CAPABLE_DRIVERS = frozenset({
    "local-persist",
    "rexray",
    "rexray/ebs",
    "netapp",
    "portworx",
    "flocker",
})


class Volume(Client):
    def __init__(
        self,
        name: str,
        size_mb: int = None,
        driver: str = "local",
        driver_opts: dict = None,
    ):
        super().__init__()
        self.name = name
        self.driver = (driver or "local").strip() or "local"
        self.size_mb = size_mb
        self.driver_opts = dict(driver_opts or {})

    def _options(self) -> dict:
        """
        Build driver_opts for volumes.create().

        Application quota (size_mb) must NOT be injected into the default
        local driver — Docker rejects unknown options and the whole deploy
        fails. Only forward size when the driver is known to support it, or
        when the caller already put a size key into driver_opts explicitly.
        """
        opts = dict(self.driver_opts)

        # Caller already set a size-related option → respect it.
        if any(k.lower() in ("size", "size_mb", "capacity") for k in opts):
            return opts

        if self.size_mb is None:
            return opts

        try:
            size_val = int(self.size_mb)
        except (TypeError, ValueError):
            return opts
        if size_val <= 0:
            return opts

        driver_key = self.driver.lower().split(":")[0]
        if driver_key in _SIZE_CAPABLE_DRIVERS or driver_key.startswith("rexray"):
            # Common convention for size-aware plugins
            opts.setdefault("size", f"{size_val}Mb")
        else:
            # local (and most other stock drivers): ignore size_mb so create()
            # succeeds. Quota is enforced in the Django Volume model only.
            logger.debug(
                "Ignoring size_mb=%s for volume '%s' (driver=%s does not "
                "support size option).",
                size_val,
                self.name,
                self.driver,
            )
        return opts

    def create(self):
        opts = self._options()
        try:
            volume = self.client.volumes.create(
                name=self.name,
                driver=self.driver,
                driver_opts=opts or None,
                labels={"managed-by": "django-paas-deployer"},
            )
            logger.info(
                "Volume '%s' created with driver '%s' opts=%s",
                self.name,
                self.driver,
                opts or {},
            )
            return volume
        except docker.errors.APIError as exc:
            if getattr(exc, "status_code", None) == 409 or "already exists" in str(exc).lower():
                return self.client.volumes.get(self.name)
            logger.error(
                "Docker API error creating volume '%s' (driver=%s, opts=%s): %s",
                self.name,
                self.driver,
                opts,
                exc,
            )
            raise VolumeError(
                f"Failed to create Docker volume '{self.name}'.",
                details={
                    "volume": self.name,
                    "driver": self.driver,
                    "driver_opts": opts,
                    "error": str(exc),
                },
            ) from exc
        except docker.errors.DockerException as exc:
            logger.error(
                "Docker error creating volume '%s' (driver=%s): %s",
                self.name,
                self.driver,
                exc,
            )
            raise VolumeError(
                f"Failed to create Docker volume '{self.name}'.",
                details={
                    "volume": self.name,
                    "driver": self.driver,
                    "driver_opts": opts,
                    "error": str(exc),
                },
            ) from exc

    def ensure(self):
        try:
            return self.client.volumes.get(self.name)
        except docker.errors.NotFound:
            return self.create()
        except docker.errors.DockerException as exc:
            logger.error(
                "Docker error inspecting volume '%s': %s", self.name, exc
            )
            raise VolumeError(
                f"Failed to inspect Docker volume '{self.name}'.",
                details={"volume": self.name, "error": str(exc)},
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
            raise VolumeError(
                f"Failed to remove Docker volume '{self.name}'.",
                details={"volume": self.name, "error": str(exc)},
            ) from exc
