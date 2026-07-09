from .manager.container_manager import Container
from .manager.image_manager import Image
from .types import DeploymentConfig


class CleanupManager:
    def __init__(self, logger=None):
        self.logger = logger

    def remove_container(self, name: str):
        container = Container(name)
        if container.exists():
            container.stop()
            container.remove()

    def remove_failed_image(self, config: DeploymentConfig):
        image = Image(config.name, str(config.tag))
        image.remove(force=True)

    def prune_dangling_images(self):
        try:
            Image.prune_dangling_images()
            if self.logger:
                self.logger.info("cleanup", "Dangling Docker images pruned.", progress=100)
        except Exception as exc:
            if self.logger:
                self.logger.warning(
                    "cleanup",
                    "Could not prune dangling Docker images.",
                    progress=100,
                    details={"error": str(exc)},
                )
