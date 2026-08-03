"""
deployments/core/orchestrator.py
---------------------------------
Main deployment pipeline with platform auto-detection integrated.
"""

from __future__ import annotations

import shutil

from .cleanup import CleanupManager
from .converter import convert_zip_to_tar
from .deployment_logger import DeploymentLogger
from .dockerfile import DockerfileGenerator
from .exceptions import DeploymentCancelled, DeploymentError
from .health import DockerHealthChecker
from .manager.container_manager import Container
from .manager.image_manager import Image
from .manager.network_manager import Network
from .platform_bridge import enrich_config_from_project, extract_zip_to_temp
from .rollback import RollbackManager
from .types import DeploymentConfig, DeploymentResult, EventSink
from .validation import DeploymentValidator
from .volumes import VolumeMountManager


class DeploymentOrchestrator:
    def __init__(self, *, event_sink: EventSink = None, deployment_id: str = None):
        self.logger = DeploymentLogger(deployment_id=deployment_id, sink=event_sink)
        self.validator = DeploymentValidator()
        self.dockerfile_generator = DockerfileGenerator()
        self.volume_manager = VolumeMountManager(logger=self.logger)
        self.health_checker = DockerHealthChecker(logger=self.logger)
        self.rollback_manager = RollbackManager(logger=self.logger)
        self.cleanup_manager = CleanupManager(logger=self.logger)

    def deploy(self, config: DeploymentConfig) -> DeploymentResult:
        previous_image_ref = None
        old_container_removed = False
        image_built = False
        volume_binds = {}
        inspect_temp_dir = None

        self.logger.info(
            "deployment_started",
            "Deployment started.",
            progress=1,
            details={"container": config.name, "image": config.image_ref},
        )

        try:
            # --------------------------------------------------------------
            # 1. Validate
            # --------------------------------------------------------------
            self.logger.info("validation", "Validating deployment configuration.", progress=5)
            self.validator.validate(config)

            # --------------------------------------------------------------
            # 2. Prepare build context (zip → tar)
            # --------------------------------------------------------------
            self.logger.info("prepare_resources", "Preparing build context.", progress=10)
            tar_stream = convert_zip_to_tar(config.zip_path)

            # --------------------------------------------------------------
            # 3. Platform auto-detection (filesystem inspect)
            #    Fills empty entry_point / server_type / port / platform
            #    without overwriting explicit user values.
            # --------------------------------------------------------------
            try:
                inspect_temp_dir, project_root = extract_zip_to_temp(config.zip_path)
                config = enrich_config_from_project(
                    config,
                    project_root,
                    logger_sink=self.logger,
                )
            except Exception as exc:
                self.logger.warning(
                    "platform_detection",
                    f"Could not inspect project tree: {exc}. "
                    "Continuing without enrichment.",
                    progress=11,
                    details={"error": str(exc)},
                )

            # --------------------------------------------------------------
            # 4. Generate Dockerfile (honours enriched entry_point/server_type)
            # --------------------------------------------------------------
            dockerfile_text = self.dockerfile_generator.render(
                platform=config.platform,
                dockerfile_template=config.dockerfile_template,
                tar_stream=tar_stream,
                config=config,
                logger=self.logger,
            )

            # --------------------------------------------------------------
            # 5. Snapshot existing container for rollback
            # --------------------------------------------------------------
            existing_container = Container(config.name)
            if existing_container.exists():
                previous_image_ref = existing_container.get_image_identifier()
                self.logger.info(
                    "state_snapshot",
                    "Captured previous container state for rollback.",
                    progress=18,
                    details={"previous_image_ref": previous_image_ref},
                )

            # --------------------------------------------------------------
            # 6. Build image
            # --------------------------------------------------------------
            self.logger.info("image_build", "Building Docker image.", progress=20)
            image = Image(config.name, str(config.tag), dockerfile_text, tar_stream)
            image.create(on_build_output=self._on_build_output)
            image_built = True
            self.logger.info(
                "image_build",
                "Docker image built successfully.",
                progress=35,
                details={"image": config.image_ref},
            )

            self._ensure_networks(config)

            self.logger.info("volume_creation", "Preparing Docker volume mounts.", progress=40)
            volume_binds = self.volume_manager.prepare(config.volumes)
            self.logger.info(
                "volume_creation",
                "Docker volume mounts are ready.",
                progress=48,
                details={"volume_count": len(config.volumes)},
            )

            replacement_container = Container(
                config.name,
                config.image_ref,
                config.max_cpu,
                config.max_ram,
                [network.name for network in config.networks],
                volume_binds,
                config.read_only,
                entry_port=config.port,
                environment=dict(config.environment) if config.environment else {},
            )

            if existing_container.exists():
                self.logger.info(
                    "container_replacement", "Stopping existing container.", progress=55
                )
                existing_container.stop(timeout=config.stop_timeout)
                self.logger.info(
                    "container_replacement", "Removing existing container.", progress=60
                )
                existing_container.remove()
                old_container_removed = True

            self.logger.info(
                "container_creation", "Creating replacement container.", progress=65
            )
            replacement_container.create()

            self.logger.info(
                "container_startup", "Starting replacement container.", progress=80
            )
            replacement_container.start()

            self.logger.info("health_check", "Verifying container health.", progress=86)
            health = self.health_checker.wait_until_healthy(
                config.name,
                timeout=config.health_timeout,
                interval=config.health_interval,
            )

            self.cleanup_manager.prune_dangling_images()
            self.logger.info(
                "deployment_completed",
                "Deployment completed successfully.",
                progress=100,
                details={"image": config.image_ref, "health": health},
            )
            return DeploymentResult(
                success=True,
                status="succeeded",
                message="Deployment completed successfully.",
                image_ref=config.image_ref,
                container_name=config.name,
                previous_image_ref=previous_image_ref,
                details={
                    "health": health,
                    "networks": [network.name for network in config.networks],
                    "volumes": [volume.target for volume in config.volumes],
                },
            )

        except DeploymentCancelled as exc:
            return self._handle_cancellation(
                config,
                exc,
                previous_image_ref=previous_image_ref,
                old_container_removed=old_container_removed,
                image_built=image_built,
                volume_binds=volume_binds,
            )
        except DeploymentError as exc:
            return self._handle_failure(
                config,
                exc,
                previous_image_ref=previous_image_ref,
                old_container_removed=old_container_removed,
                image_built=image_built,
                volume_binds=volume_binds,
            )
        except Exception as exc:
            wrapped = DeploymentError(
                "Unexpected deployment failure.",
                stage="deployment",
                details={"error": str(exc)},
            )
            return self._handle_failure(
                config,
                wrapped,
                previous_image_ref=previous_image_ref,
                old_container_removed=old_container_removed,
                image_built=image_built,
                volume_binds=volume_binds,
            )
        finally:
            if inspect_temp_dir:
                shutil.rmtree(inspect_temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Cancellation / failure / helpers (unchanged behaviour)
    # ------------------------------------------------------------------

    def _handle_cancellation(
        self,
        config: DeploymentConfig,
        exc: DeploymentCancelled,
        *,
        previous_image_ref,
        old_container_removed,
        image_built,
        volume_binds,
    ) -> DeploymentResult:
        rollback_performed = False
        if old_container_removed:
            try:
                rollback_performed = self.rollback_manager.restore_previous_container(
                    config,
                    previous_image_ref=previous_image_ref,
                    volume_binds=volume_binds,
                )
            except DeploymentError:
                pass
        if image_built:
            try:
                self.cleanup_manager.remove_failed_image(config)
            except DeploymentError:
                pass
        return DeploymentResult(
            success=False,
            status="cancelled",
            message=exc.message,
            image_ref=config.image_ref,
            container_name=config.name,
            previous_image_ref=previous_image_ref,
            rollback_performed=rollback_performed,
            error=exc.message,
            stage="cancelled",
        )

    def _ensure_networks(self, config: DeploymentConfig):
        self.logger.info("network_creation", "Ensuring Docker networks exist.", progress=36)
        for spec in config.networks:
            Network(
                spec.name,
                spec.driver,
                internal=spec.internal,
                attachable=spec.attachable,
            ).ensure()
            self.logger.info(
                "network_creation",
                f"Network '{spec.name}' is ready.",
                progress=38,
                details={"network": spec.name, "internal": spec.internal},
            )

    def _on_build_output(self, chunk):
        if "stream" in chunk:
            message = chunk["stream"].strip()
            if message:
                self.logger.info("image_build", message, progress=25)
        elif "status" in chunk:
            status = chunk.get("status")
            progress = chunk.get("progress")
            message = f"{status} {progress}".strip() if progress else status
            self.logger.info(
                "image_build", message, progress=25, details={"docker_status": status}
            )
        elif "error" in chunk:
            self.logger.error(
                "image_build",
                chunk.get("error"),
                progress=25,
                details={"docker_build_error": chunk},
            )

    def _handle_failure(
        self,
        config: DeploymentConfig,
        exc: DeploymentError,
        *,
        previous_image_ref,
        old_container_removed,
        image_built,
        volume_binds,
    ) -> DeploymentResult:
        rollback_performed = False
        self.logger.error(
            exc.stage,
            exc.message,
            progress=95,
            details={**exc.details, "recoverable": exc.recoverable},
        )

        if old_container_removed:
            try:
                self.logger.warning("rollback", "Starting rollback.", progress=96)
                rollback_performed = self.rollback_manager.restore_previous_container(
                    config,
                    previous_image_ref=previous_image_ref,
                    volume_binds=volume_binds,
                )
            except DeploymentError as rollback_exc:
                self.logger.error(
                    "rollback",
                    rollback_exc.message,
                    progress=99,
                    details=rollback_exc.details,
                )

        if image_built:
            try:
                self.cleanup_manager.remove_failed_image(config)
            except Exception as cleanup_exc:
                self.logger.warning(
                    "cleanup",
                    "Failed to remove unsuccessful deployment image.",
                    progress=99,
                    details={"error": str(cleanup_exc), "image": config.image_ref},
                )

        self.cleanup_manager.prune_dangling_images()
        self.logger.error(
            "deployment_failed",
            "Deployment failed.",
            progress=100,
            details={"stage": exc.stage, "rollback_performed": rollback_performed},
        )
        return DeploymentResult(
            success=False,
            status="failed",
            message=exc.message,
            image_ref=config.image_ref,
            container_name=config.name,
            previous_image_ref=previous_image_ref,
            rollback_performed=rollback_performed,
            error=exc.message,
            stage=exc.stage,
            details=exc.details,
        )
