from os import read
from .client_manager import Client
import logging
import docker
logger = logging.getLogger(__name__)

class Container(Client):
    def __init__(self, name: str, image_name: str, max_cpu: float, max_ram: int, networks: list,
                 volumes: dict = None, read_only: bool = True, command: str = None, environment: dict = None,
                 exposed_ports: dict = None, port_bindings: dict = None):
        super().__init__()
        self.name = name
        self.image_name = image_name
        self.max_cpu = max_cpu
        self.max_ram = max_ram
        self.networks = networks
        self.volumes = volumes or {}
        self.read_only = read_only
        self.command = command
        self.environment = environment or {}
        self.exposed_ports = exposed_ports or {}
        self.port_bindings = port_bindings or {}
        if not self.networks:
            raise ValueError("At least one network is required to create a container.")

    def create(self):
        try:
            host_config = self.client.api.create_host_config(
                cpu_quota=int(self.max_cpu * 100000),
                mem_limit=f"{self.max_ram}m",
                binds=self.volumes,
                port_bindings=self.port_bindings,
                read_only=self.read_only,
                
            )
            # Networking
            endpoints_config = {net: {} for net in self.networks}
            networking_config = self.client.api.create_networking_config(endpoints_config)
            # Create container
            container = self.client.api.create_container(
                name=self.name,
                image=self.image_name,
                command=self.command,
                environment=self.environment,
                host_config=host_config,
                networking_config=networking_config,
                ports=self.exposed_ports, 
            )
            logger.info(f"Service '{self.name}' created from image '{self.image_name}' on networks {self.networks}")
            return container
        except Exception as e:
            logger.error(f"Failed to create container '{self.name}': {e}")
            raise

    def start(self):
        try:
            container = self.client.containers.get(self.name)
            container.start()
            logger.info(f"Service '{self.name}' started successfully")
        except Exception as e:
            logger.error(f"Failed to start container '{self.name}': {e}")
            raise
        
    def stop(self, timeout=5):
        try:
            container = self.client.containers.get(self.name)

            if container.status != "running":
                logger.info(f"Service '{self.name}' is not running (status={container.status})")
                return

            container.stop(timeout=timeout)
            logger.info(f"Service '{self.name}' stopped successfully")

        except docker.errors.NotFound:
            # idempotent behavior
            logger.info(f"Service '{self.name}' does not exist, nothing to stop")

        except docker.errors.APIError as e:
            logger.error(f"Docker API error while stopping container '{self.name}': {e}")
            raise

        except Exception as e:
            logger.exception(f"Unexpected error while stopping container '{self.name}'")
            raise
        
    @classmethod
    def container_is_running(cls, container_name: str) -> bool:
        client = Client().client
        try:
            container = client.containers.get(container_name)
            return container.status == "running"
        except docker.errors.NotFound:
            # Service not found
            return False
        except Exception as e:
            # Log unexpected errors
            logger.error(f"Error while checking container '{container_name}': {e}")
            raise

    def remove(self):
        try:
            if container := self.client.containers.get(self.name):
                container.remove(force=True)
                logger.info(f"Service '{self.name}' deleted successfully")
            else:
                logger.info(f"Service '{self.name}' not found")
            return True
        except Exception as e:
            logger.error(f"Failed to remove container '{self.name}': {e}")
            raise
        
    def exists(self) -> bool:
        """
        Check if a container with this name exists (running or stopped).
        """
        try:
            self.client.containers.get(self.name)
            return True
        except docker.errors.NotFound:
            return False
        except Exception as e:
            logger.error(f"Error checking existence of container '{self.name}': {e}")
            raise
