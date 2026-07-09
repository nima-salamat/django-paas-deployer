import logging

import docker

from .client_manager import Client
from deployments.core.exceptions import NetworkError

logger = logging.getLogger(__name__)


class Network(Client):
    def __init__(self, name: str, driver: str = "bridge", *, internal: bool = True, attachable: bool = True):
        super().__init__()
        self.name = name
        self.driver = driver or "bridge"
        self.internal = internal
        self.attachable = attachable

    def create(self) -> docker.models.networks.Network:
        try:
            network = self.client.networks.create(
                name=self.name,
                driver=self.driver,
                internal=self.internal,
                attachable=self.attachable,
                check_duplicate=True,
                labels={"managed-by": "django-paas-deployer"},
            )
            logger.info("Network '%s' created with driver '%s'", self.name, self.driver)
            return network
        except docker.errors.APIError as exc:
            if getattr(exc, "status_code", None) == 409 or "already exists" in str(exc):
                return self.client.networks.get(self.name)
            raise NetworkError(
                f"Failed to create Docker network '{self.name}'.",
                details={"network": self.name, "driver": self.driver},
            ) from exc
        except docker.errors.DockerException as exc:
            raise NetworkError(
                f"Failed to create Docker network '{self.name}'.",
                details={"network": self.name, "driver": self.driver},
            ) from exc

    def ensure(self):
        try:
            return self.client.networks.get(self.name)
        except docker.errors.NotFound:
            return self.create()
        except docker.errors.DockerException as exc:
            raise NetworkError(
                f"Failed to inspect Docker network '{self.name}'.",
                details={"network": self.name},
            ) from exc

    @classmethod
    def network_exists(cls, network_name: str) -> bool:
        client = Client()()
        try:
            client.networks.get(network_name)
            return True
        except docker.errors.NotFound:
            return False
        except docker.errors.DockerException as exc:
            raise NetworkError(
                f"Failed to check Docker network '{network_name}'.",
                details={"network": network_name},
            ) from exc

    def remove(self):
        try:
            network = self.client.networks.get(self.name)
        except docker.errors.NotFound:
            logger.info("Network '%s' not found; nothing to remove.", self.name)
            return True

        try:
            network.remove()
            logger.info("Network '%s' deleted.", self.name)
            return True
        except docker.errors.DockerException as exc:
            raise NetworkError(f"Failed to remove Docker network '{self.name}'.") from exc
