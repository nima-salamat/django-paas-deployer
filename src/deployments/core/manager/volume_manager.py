import logging
import os
import shutil

import docker

from .client_manager import Client
from deployments.core.exceptions import VolumeError

logger = logging.getLogger(__name__)


# Docker driver capabilities are intentionally conservative.
#
# Volume.size_mb is logical allocation metadata. It is never converted
# into a Docker driver option merely because a driver name appears on an
# allow-list: accepting a size option does not prove that a backend
# physically enforces a persistent capacity. Trusted operator/catalog
# definitions may still provide explicitly validated driver_opts.


# Minimum free space (MB) that must remain on the Docker root filesystem
# after allocating a new volume. Prevents the host from filling up.
_MIN_FREE_AFTER_MB = 512


class Volume(Client):
    def __init__(
        self,
        name: str,
        size_mb: int = None,
        driver: str = "local",
        driver_opts: dict = None,
        require_managed: bool = False,
    ):
        super().__init__()
        self.name = name
        self.driver = (driver or "local").strip() or "local"
        self.size_mb = size_mb
        self.driver_opts = dict(driver_opts or {})
        self.require_managed = bool(require_managed)

    def _options(self) -> dict:
        """
        Build operator/catalog-controlled driver options for volumes.create().

        ``size_mb`` is application-level logical capacity metadata. It is never
        inferred into a driver option from a driver name. Explicit backend
        options remain trusted configuration and are not treated as proof of
        physical quota enforcement.
        """
        opts = dict(self.driver_opts)

        # Explicit driver options are trusted operator/catalog configuration
        # only. size_mb itself is never translated into a driver option.
        # Accepting an option does not prove physical enforcement.
        if any(k.lower() in ("size", "size_mb", "capacity") for k in opts):
            logger.debug(
                "Using explicit storage capacity option for volume '%s' "
                "(driver=%s); physical enforcement remains backend-specific.",
                self.name,
                self.driver,
            )
        return opts

    @staticmethod
    def check_host_space(required_mb: int | None = None) -> tuple[bool, int]:
        """
        Return (ok, free_mb) for the Docker root filesystem.

        When ``required_mb`` is given we also require that after allocation
        at least ``_MIN_FREE_AFTER_MB`` remains. This is a best-effort host
        check; the local driver has no hard size quota.
        """
        try:
            # Prefer Docker root dir when available
            info = None
            try:
                from .client_manager import Client as _C
                info = _C().client.info()
            except Exception:
                pass
            configured_root = os.environ.get("DOCKER_HOST_STORAGE_PATH", "").strip()
            root = configured_root or (info or {}).get("DockerRootDir") or "/var/lib/docker"
            usage = shutil.disk_usage(root)
            free_mb = usage.free // (1024 * 1024)
            if required_mb is None or required_mb <= 0:
                return free_mb >= _MIN_FREE_AFTER_MB, free_mb
            needed = int(required_mb) + _MIN_FREE_AFTER_MB
            return free_mb >= needed, free_mb
        except Exception as exc:
            logger.warning(
                "Host disk-space check failed for Docker storage path '%s': %s",
                root if "root" in locals() else "<unresolved>",
                exc,
            )
            # Storage safety cannot be proven when the Docker root filesystem
            # cannot be inspected. Do not silently proceed with a persistent
            # volume whose host capacity is unknown.
            return False, -1

    def create(self):
        opts = self._options()
        # Pre-flight space check (non-fatal when size_mb is unknown)
        ok, free_mb = self.check_host_space(self.size_mb)
        if not ok:
            if free_mb < 0:
                raise VolumeError(
                    f"Cannot verify host disk space before creating volume '{self.name}'.",
                    details={
                        "volume": self.name,
                        "free_mb": None,
                        "requested_mb": self.size_mb,
                        "min_reserve_mb": _MIN_FREE_AFTER_MB,
                        "check": "unavailable",
                    },
                )
            raise VolumeError(
                f"Insufficient host disk space to create volume '{self.name}'. "
                f"Free={free_mb} MB, requested={self.size_mb or '?'} MB "
                f"(minimum reserve {_MIN_FREE_AFTER_MB} MB).",
                details={
                    "volume": self.name,
                    "free_mb": free_mb,
                    "requested_mb": self.size_mb,
                    "min_reserve_mb": _MIN_FREE_AFTER_MB,
                    "check": "best_effort_preflight",
                },
            )
        try:
            volume = self.client.volumes.create(
                name=self.name,
                driver=self.driver,
                driver_opts=opts or None,
                labels={"managed-by": "django-paas-deployer", "volume.name": self.name},
            )
            logger.info(
                "Volume '%s' created with driver '%s' opts=%s (host free ~%s MB)",
                self.name,
                self.driver,
                opts or {},
                free_mb,
            )
            return volume
        except docker.errors.APIError as exc:
            if getattr(exc, "status_code", None) == 409 or "already exists" in str(exc).lower():
                volume = self.client.volumes.get(self.name)
                labels = dict(getattr(volume, "attrs", {}).get("Labels") or {})
                if labels.get("managed-by") != "django-paas-deployer":
                    raise VolumeError(
                        f"Docker volume '{self.name}' exists but is not owned by PassDeployer.",
                        details={"volume": self.name, "labels": labels},
                    )
                return volume
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
            volume = self.client.volumes.get(self.name)
            if self.require_managed:
                labels = dict(getattr(volume, "attrs", {}).get("Labels") or {})
                if labels.get("managed-by") != "django-paas-deployer":
                    raise VolumeError(
                        f"Docker volume '{self.name}' exists but is not owned by PassDeployer.",
                        details={"volume": self.name, "labels": labels},
                    )
            return volume
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
