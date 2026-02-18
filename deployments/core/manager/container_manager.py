from os import read
from .client_manager import Client
import logging
import docker
logger = logging.getLogger(__name__)

class Container(Client):
    def __init__(self, name: str, image_name: str=None, max_cpu: float=None, max_ram: int=None, networks: list=None,
                 volumes: dict = None, read_only: bool = True, command: str = None, environment: dict = None,
                 exposed_ports: dict = None, port_bindings: dict = None, entry_port=None):
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
        self.entry_port = entry_port
        

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
            labels = {
                "traefik.enable": "true",
                "traefik.docker.network": "proxy_net",
                # Router
                f"traefik.http.routers.{self.name}.rule":
                    f"Host(`{self.name}.local`)",
                f"traefik.http.routers.{self.name}.entrypoints": "web",
                f"traefik.http.routers.{self.name}.service": self.name,

                # Service
                f"traefik.http.services.{self.name}.loadbalancer.server.port":
                    str(self.entry_port),
            }

            container = self.client.api.create_container(
                name=self.name,
                image=self.image_name,
                command=self.command,
                environment=self.environment,
                host_config=host_config,
                networking_config=networking_config,
                ports=self.exposed_ports, 
                labels=labels,
                
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
            container.reload()
            logger.info("Service '%s' started; status=%s", self.name, container.status)
        except docker.errors.NotFound:
            logger.error("Container %s not found on start()", self.name)
            raise
        except Exception:
            logger.exception("Failed to start container %s", self.name)
            raise

    def stop(self, timeout=5):
        try:
            container = self.client.containers.get(self.name)
        except docker.errors.NotFound:
            logger.info("Service '%s' does not exist, nothing to stop", self.name)
            return

        try:
            if container.status != "running":
                logger.info("Service '%s' is not running (status=%s)", self.name, container.status)
                return
            container.stop(timeout=timeout)
            logger.info("Service '%s' stopped successfully", self.name)
        except docker.errors.APIError:
            logger.exception("Docker API error while stopping container '%s'", self.name)
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

    def is_running(self):
        
        return Container.container_is_running(self.name)

    def get_exit_code(self):
        try:
            container = self.client.containers.get(self.name)
            container.reload()

            state = container.attrs.get("State", {})

            if state.get("Running"):
                return None

            return state.get("ExitCode")

        except docker.errors.NotFound:
            return None
        except Exception:
            return None
    
    def remove(self):
        try:
            container = self.client.containers.get(self.name)
        except docker.errors.NotFound:
            logger.info("Service '%s' not found (nothing to remove)", self.name)
            return True
        try:
            container.remove(force=True)
            logger.info("Service '%s' deleted successfully", self.name)
            return True
        except Exception:
            logger.exception("Failed to remove container '%s'", self.name)
            return False
        
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
