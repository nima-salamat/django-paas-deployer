from .client_manager import Client
import docker
import logging

logger = logging.getLogger(__name__)


class Network(Client):
       
    def __init__(self, name: str, driver: str = "bridge"):
        super().__init__()
        self.name = name
        self.driver = driver
    
    def create(self) -> docker.models.networks.Network:
        try:
            network = self.client.networks.create(
                name=self.name,
                driver=self.driver,
                internal=True
            )
            logger.info(f"Network '{self.name}' created successfully with driver '{self.driver}'")
            return network
        
        except docker.errors.DockerException as e:
            logger.error(f"Failed to create network '{self.name}' : {e}")
            raise
        
        
    @classmethod
    def network_exists(cls, network_name: str) -> bool:
        client = Client()()
        try:
            client.networks.get(network_name)
            return True
        except docker.errors.NotFound:
            # Network not found
            return False
        except Exception as e:
            # Log unexpected errors
            logger.error(f"Error while checking network '{network_name}': {e}")
            raise
        
    
    
    def remove(self):
        try:
            if network:=self.client.networks.get(self.name):
                network.remove()
                logger.info(f"Network '{self.name}' deleted successfully")
            else:
                logger.info(f"Network '{self.name}' not found")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove network '{self.name}' : {e}")
            raise        