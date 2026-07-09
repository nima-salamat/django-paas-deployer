import logging

import docker

logger = logging.getLogger(__name__)


class Client:
    def __init__(self, base_url=None):
        try:
            self.client = docker.DockerClient(base_url=base_url) if base_url else docker.from_env()
            self.client.ping()
        except docker.errors.DockerException as exc:
            logger.exception("Failed to create Docker client.")
            raise exc

    def __call__(self):
        return self.client
