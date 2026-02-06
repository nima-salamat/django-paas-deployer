from .client_manager import Client
import logging

logger = logging.getLogger(__name__)

class Volume(Client):
    def __init__(self, name: str, size_mb: int, driver: str = "rexray", driver_opts: dict = None):
        super().__init__()
        self.name = name
        self.driver = driver
        self.size_mb = size_mb
        self.driver_opts = driver_opts or {}

    def create(self):
        opts = {**self.driver_opts, "size": f"{self.size_mb}Mb"}

        try:
            volume = self.client.volumes.create(
                name=self.name,
                driver=self.driver,
                driver_opts=opts
            )
            logger.info(f"Volume '{self.name}' created with driver '{self.driver}' and size {self.size_mb}Mb")
            return volume
        except Exception as e:
            logger.error(f"Failed to create volume '{self.name}': {e}")
            raise

    def remove(self):
        try:
        
            if volume:=self.client.volumes.get(self.name):
                volume.remove()
                logger.info(f"Volume '{self.name}' deleted")
            else:
                logger.info(f"Volume '{self.name}' not found")
            return True
                
                
        
        except Exception as e:
            logger.error(f"Failed to create volume '{self.name}': {e}")
            raise