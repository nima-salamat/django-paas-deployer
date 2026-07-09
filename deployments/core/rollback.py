from .exceptions import RollbackError
from .manager.container_manager import Container
from .types import DeploymentConfig


class RollbackManager:
    def __init__(self, logger=None):
        self.logger = logger

    def restore_previous_container(
        self,
        config: DeploymentConfig,
        *,
        previous_image_ref: str,
        volume_binds: dict,
    ) -> bool:
        if not previous_image_ref:
            if self.logger:
                self.logger.warning("rollback", "No previous image is available for rollback.", progress=96)
            return False

        try:
            current = Container(config.name)
            if current.exists():
                current.stop(timeout=config.stop_timeout)
                current.remove()

            restored = Container(
                config.name,
                previous_image_ref,
                config.max_cpu,
                config.max_ram,
                [network.name for network in config.networks],
                volume_binds,
                config.read_only,
                entry_port=config.port,
            )
            restored.create()
            restored.start()

            if self.logger:
                self.logger.info(
                    "rollback",
                    "Rollback restored the previous container image.",
                    progress=98,
                    details={"previous_image_ref": previous_image_ref},
                )
            return True
        except Exception as exc:
            raise RollbackError(
                "Rollback failed while restoring the previous container.",
                details={"previous_image_ref": previous_image_ref},
            ) from exc
