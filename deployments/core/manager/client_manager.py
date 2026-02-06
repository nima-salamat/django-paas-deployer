import docker
import logging

logger = logging.getLogger(__name__)

class Client:
    def __init__(self, base_url='unix://var/run/docker.sock'):
        self.client = None
        try:
            self.client =docker.DockerClient(base_url=base_url)
        except docker.errors.DockerException as e:
            logger.error(f"e")
            raise
        
    def __call__(self):
        return self.client
    
