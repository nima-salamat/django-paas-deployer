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
        """Do not globally prune the Docker daemon from an individual deploy.

        A deployment worker shares the Docker host with unrelated deployments
        and concurrent builds. Global dangling-image pruning is therefore not
        an ownership-safe cleanup operation. Per-deployment cleanup removes the
        failed image explicitly; host-wide garbage collection belongs to a
        separate operator-controlled maintenance task.
        """
        if self.logger:
            self.logger.info(
                "cleanup",
                "Skipped global dangling-image prune; host-wide Docker GC is operator-managed.",
                progress=100,
            )
        return False
