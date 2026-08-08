"""
deployments/core/orchestrator.py
--------------------------------
Deployment orchestrator — the pipeline that takes a DeploymentConfig
end-to-end from validation to a running healthy container.

Key changes vs. legacy:
  * ``ContainerSnapshot.capture()`` is taken BEFORE any mutation so
    rollback can restore the EXACT previous state (env, command, labels,
    restart_policy) instead of just image + networks.
  * Container replacement uses the rename-old strategy: rename the old
    container out of the way, create + start the new one, then remove
    the old.  This eliminates the stop-old → create-new downtime window
    AND means rollback can simply rename the old container back if
    create/start fails.
  * Rollback failures are NO LONGER SWALLOWED.  The DeploymentResult
    carries ``rollback_performed`` and ``rollback_failed`` so the caller
    can mark the deploy appropriately.
  * Mid-deployment cancellation is now supported via cancellation
    tokens checked between stages.
  * ``prune_dangling_images`` failures are logged but do not mask the
    deploy result.
"""

from __future__ import annotations

import shutil
from typing import Optional

from .cleanup import CleanupManager
from .converter import convert_zip_to_tar
from .deployment_logger import DeploymentLogger
from .dockerfile import DockerfileGenerator
from deployments.common.exceptions import (
    DeploymentCancelled,
    DeploymentError,
    RollbackError,
)
from .health import DockerHealthChecker
from .manager.container_manager import Container
from .manager.image_manager import Image
from .manager.network_manager import Network
from .platform_bridge import enrich_config_from_project, extract_zip_to_temp
from .rollback import ContainerSnapshot, RollbackManager
from .types import DeploymentConfig, DeploymentResult, EventSink
from .validation import DeploymentValidator
from .volumes import VolumeMountManager


class DeploymentOrchestrator:
    def __init__(
        self,
        *,
        event_sink: EventSink = None,
        deployment_id: Optional[str] = None,
        cancel_check: Optional[callable] = None,
    ):
        """
        Parameters
        ----------
        event_sink
            Callable that receives ``DeploymentEvent`` instances for
            streaming logs / progress.
        deployment_id
            Correlation ID included in every log record.
        cancel_check
            Optional zero-arg callable returning True if the deployment
            has been cancelled.  Checked between stages.
        """
        self.logger = DeploymentLogger(deployment_id=deployment_id, sink=event_sink)
        self.validator = DeploymentValidator()
        self.dockerfile_generator = DockerfileGenerator()
        self.volume_manager = VolumeMountManager(logger=self.logger)
        self.health_checker = DockerHealthChecker(logger=self.logger)
        self.rollback_manager = RollbackManager(logger=self.logger)
        self.cleanup_manager = CleanupManager(logger=self.logger)
        self._cancel_check = cancel_check

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def deploy(self, config: DeploymentConfig) -> DeploymentResult:
        snapshot: ContainerSnapshot = ContainerSnapshot.empty(config.name)
        image_built = False
        volume_binds: dict = {}
        inspect_temp_dir = None
        new_container_started = False
        renamed_old_name: str | None = None

        self.logger.info(
            "deployment_started",
            "Deployment started.",
            progress=1,
            details={"container": config.name, "image": config.image_ref},
        )

        try:
            self._check_cancelled()

            # 1. Validate
            self.logger.info("validation", "Validating deployment configuration.", progress=5)
            self.validator.validate(config)

            self._check_cancelled()

            # 2. Build context (zip -> tar)
            self.logger.info("prepare_resources", "Preparing build context.", progress=10)
            tar_stream = convert_zip_to_tar(config.zip_path)

            # 3. Platform auto-detection
            try:
                inspect_temp_dir, project_root = extract_zip_to_temp(config.zip_path)
                config = enrich_config_from_project(
                    config, project_root, logger_sink=self.logger,
                )
            except Exception as exc:
                self.logger.warning(
                    "platform_detection",
                    f"Could not inspect project tree: {exc}. Continuing without enrichment.",
                    progress=11,
                    details={"error": str(exc)},
                )

            self._check_cancelled()

            # 4. Generate Dockerfile
            dockerfile_text = self.dockerfile_generator.render(
                platform=config.platform,
                dockerfile_template=config.dockerfile_template,
                tar_stream=tar_stream,
                config=config,
                logger=self.logger,
            )

            # 5. Snapshot existing container for rollback (BEFORE any mutation)
            existing_container = Container(config.name)
            if existing_container.exists():
                snapshot = ContainerSnapshot.capture(existing_container)
                self.logger.info(
                    "state_snapshot",
                    "Captured previous container state for rollback.",
                    progress=18,
                    details={
                        "previous_image_ref": snapshot.image_ref,
                        "network_count": len(snapshot.networks),
                        "env_keys": sorted(snapshot.environment.keys()),
                    },
                )
            else:
                snapshot = ContainerSnapshot.empty(config.name)

            self._check_cancelled()

            # 6. Build image
            self.logger.info("image_build", "Building Docker image.", progress=20)
            image = Image(
                config.name, str(config.tag), dockerfile_text, tar_stream,
                max_cpu=config.max_cpu, max_ram=config.max_ram,
            )
            image.create(on_build_output=self._on_build_output)
            image_built = True
            self.logger.info(
                "image_build", "Docker image built successfully.",
                progress=35, details={"image": config.image_ref},
            )

            self._check_cancelled()

            # 7. Networks + volumes
            self._ensure_networks(config)
            self.logger.info("volume_creation", "Preparing Docker volume mounts.", progress=40)
            volume_binds = self.volume_manager.prepare(config.volumes)
            self.logger.info(
                "volume_creation", "Docker volume mounts are ready.",
                progress=48, details={"volume_count": len(config.volumes)},
            )

            self._check_cancelled()

            # 8. Container replacement — RENAME-OLD strategy
            # Rename the existing container out of the way BEFORE creating
            # the new one.  This:
            #   * Eliminates the stop-old -> create-new downtime window
            #     (the old container stays running until the new one is
            #     ready to take traffic).
            #   * Means rollback on create/start failure is just: stop+
            #     remove the half-built new container, rename the old
            #     one back.  No image rebuild needed.
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
                renamed_old_name = f"{config.name}-old-{int(__import__('time').time())}"
                self.logger.info(
                    "container_replacement",
                    f"Renaming existing container to '{renamed_old_name}'.",
                    progress=55,
                )
                existing_container.rename(renamed_old_name)

            self.logger.info(
                "container_creation", "Creating replacement container.", progress=65
            )
            try:
                replacement_container.create()
            except DeploymentError:
                # Rollback the rename so the old container resumes traffic.
                if renamed_old_name:
                    self._undo_rename(renamed_old_name, config.name)
                raise

            self.logger.info(
                "container_startup", "Starting replacement container.", progress=80
            )
            try:
                replacement_container.start()
                new_container_started = True
            except DeploymentError:
                # New container was created but failed to start.  Remove
                # it, then rename the old one back.
                try:
                    replacement_container.remove()
                except Exception as cleanup_exc:
                    self.logger.warning(
                        "cleanup",
                        f"Failed to remove failed replacement container: {cleanup_exc}",
                        progress=82,
                    )
                if renamed_old_name:
                    self._undo_rename(renamed_old_name, config.name)
                raise

            # 9. Health check
            self.logger.info("health_check", "Verifying container health.", progress=86)
            health = self.health_checker.wait_until_healthy(
                config.name,
                timeout=config.health_timeout,
                interval=config.health_interval,
            )

            # 10. Cleanup old container + prune dangling images
            if renamed_old_name:
                self._cleanup_old_container(renamed_old_name, config.stop_timeout)

            try:
                self.cleanup_manager.prune_dangling_images()
            except Exception as exc:
                self.logger.warning(
                    "cleanup",
                    f"Failed to prune dangling images: {exc}",
                    progress=99,
                )

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
                previous_image_ref=snapshot.image_ref,
                details={
                    "health": health,
                    "networks": [network.name for network in config.networks],
                    "volumes": [volume.target for volume in config.volumes],
                },
            )

        except DeploymentCancelled as exc:
            return self._handle_cancellation(
                config, exc,
                snapshot=snapshot,
                image_built=image_built,
                volume_binds=volume_binds,
                new_container_started=new_container_started,
                renamed_old_name=renamed_old_name,
            )
        except DeploymentError as exc:
            return self._handle_failure(
                config, exc,
                snapshot=snapshot,
                image_built=image_built,
                volume_binds=volume_binds,
                new_container_started=new_container_started,
                renamed_old_name=renamed_old_name,
            )
        except Exception as exc:
            wrapped = DeploymentError(
                "Unexpected deployment failure.",
                stage="deployment",
                details={"error": str(exc), "error_type": type(exc).__name__},
            )
            return self._handle_failure(
                config, wrapped,
                snapshot=snapshot,
                image_built=image_built,
                volume_binds=volume_binds,
                new_container_started=new_container_started,
                renamed_old_name=renamed_old_name,
            )
        finally:
            if inspect_temp_dir:
                shutil.rmtree(inspect_temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def _check_cancelled(self) -> None:
        if self._cancel_check is None:
            return
        try:
            if self._cancel_check():
                raise DeploymentCancelled(
                    "Deployment cancelled by user request.",
                    stage="cancelled",
                )
        except DeploymentCancelled:
            raise
        except Exception:
            # A broken cancel_check must never crash the deploy.
            return

    # ------------------------------------------------------------------
    # Failure / cancellation handlers
    # ------------------------------------------------------------------

    def _handle_cancellation(
        self,
        config: DeploymentConfig,
        exc: DeploymentCancelled,
        *,
        snapshot: ContainerSnapshot,
        image_built: bool,
        volume_binds: dict,
        new_container_started: bool,
        renamed_old_name: str | None = None,
    ) -> DeploymentResult:
        rollback_performed = False
        rollback_failed = False

        # If the new container was started but cancelled mid-health-check,
        # we still try to roll back to the previous image.
        if snapshot.image_ref and not new_container_started:
            # Nothing to undo — old container was never renamed.
            pass
        elif snapshot.image_ref:
            # Clean up the renamed-old container first so the name is free
            # for restore_from_snapshot to use.
            if renamed_old_name:
                self._cleanup_old_container(renamed_old_name, config.stop_timeout)
            try:
                rollback_performed = self.rollback_manager.restore_from_snapshot(
                    snapshot, stop_timeout=config.stop_timeout,
                )
            except RollbackError as rollback_exc:
                rollback_failed = True
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
                    f"Failed to remove cancelled-deploy image: {cleanup_exc}",
                    progress=99,
                )

        return DeploymentResult(
            success=False,
            status="cancelled",
            message=exc.message,
            image_ref=config.image_ref,
            container_name=config.name,
            previous_image_ref=snapshot.image_ref,
            rollback_performed=rollback_performed,
            rollback_failed=rollback_failed,
            error=exc.message,
            stage="cancelled",
        )

    def _handle_failure(
        self,
        config: DeploymentConfig,
        exc: DeploymentError,
        *,
        snapshot: ContainerSnapshot,
        image_built: bool,
        volume_binds: dict,
        new_container_started: bool,
        renamed_old_name: str | None = None,
    ) -> DeploymentResult:
        rollback_performed = False
        rollback_failed = False

        self.logger.error(
            exc.stage,
            exc.message,
            progress=95,
            details={**exc.details, "recoverable": exc.recoverable},
        )

        # If the new container was started but failed health check, we
        # must stop+remove it before rolling back so the name is free.
        if new_container_started:
            try:
                failed_container = Container(config.name)
                if failed_container.exists():
                    failed_container.stop(timeout=config.stop_timeout)
                    failed_container.remove()
            except Exception as cleanup_exc:
                self.logger.warning(
                    "cleanup",
                    f"Failed to remove failed new container: {cleanup_exc}",
                    progress=97,
                )

        # Clean up the renamed-old container too — restore_from_snapshot
        # will recreate the container at the original name from the
        # snapshot, so we don't need the renamed one.
        if renamed_old_name:
            self._cleanup_old_container(renamed_old_name, config.stop_timeout)

        if snapshot.image_ref:
            try:
                self.logger.warning("rollback", "Starting rollback.", progress=96)
                rollback_performed = self.rollback_manager.restore_from_snapshot(
                    snapshot, stop_timeout=config.stop_timeout,
                )
            except RollbackError as rollback_exc:
                rollback_failed = True
                self.logger.error(
                    "rollback",
                    rollback_exc.message,
                    progress=99,
                    details=rollback_exc.details,
                )
        else:
            self.logger.warning(
                "rollback",
                "No previous container to roll back to (first deploy).",
                progress=96,
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

        try:
            self.cleanup_manager.prune_dangling_images()
        except Exception as exc2:
            self.logger.warning(
                "cleanup",
                f"Failed to prune dangling images: {exc2}",
                progress=99,
            )

        self.logger.error(
            "deployment_failed",
            "Deployment failed.",
            progress=100,
            details={
                "stage": exc.stage,
                "rollback_performed": rollback_performed,
                "rollback_failed": rollback_failed,
            },
        )
        return DeploymentResult(
            success=False,
            status="failed",
            message=exc.message,
            image_ref=config.image_ref,
            container_name=config.name,
            previous_image_ref=snapshot.image_ref,
            rollback_performed=rollback_performed,
            rollback_failed=rollback_failed,
            error=exc.message,
            stage=exc.stage,
            details={
                **exc.details,
                "rollback_performed": rollback_performed,
                "rollback_failed": rollback_failed,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_networks(self, config: DeploymentConfig):
        self.logger.info("network_creation", "Ensuring Docker networks exist.", progress=36)
        for spec in config.networks:
            Network(
                spec.name, spec.driver,
                internal=spec.internal, attachable=spec.attachable,
            ).ensure()
            self.logger.info(
                "network_creation",
                f"Network '{spec.name}' is ready.",
                progress=38,
                details={"network": spec.name, "internal": spec.internal},
            )

    def _undo_rename(self, renamed_old_name: str, original_name: str) -> None:
        """Rename the old container back to its original name."""
        try:
            old = Container(renamed_old_name)
            if old.exists():
                old.rename(original_name)
                self.logger.info(
                    "container_replacement",
                    f"Renamed '{renamed_old_name}' back to '{original_name}'.",
                    progress=62,
                )
        except Exception as exc:
            self.logger.error(
                "rollback",
                f"Failed to undo rename '{renamed_old_name}' -> '{original_name}': {exc}",
                progress=99,
                details={"renamed_old_name": renamed_old_name, "error": str(exc)},
            )

    def _cleanup_old_container(self, renamed_old_name: str, stop_timeout: int) -> None:
        """Stop + remove the renamed-old container after the new one is healthy."""
        try:
            old = Container(renamed_old_name)
            if old.exists():
                old.stop(timeout=stop_timeout)
                old.remove()
                self.logger.info(
                    "cleanup",
                    f"Removed old container '{renamed_old_name}'.",
                    progress=98,
                )
        except Exception as exc:
            self.logger.warning(
                "cleanup",
                f"Failed to remove old container '{renamed_old_name}': {exc}",
                progress=99,
                details={"renamed_old_name": renamed_old_name, "error": str(exc)},
            )

    def _on_build_output(self, chunk):
        """Forward docker build stream to DeploymentLogger."""
        if "stream" in chunk:
            message = (chunk.get("stream") or "").strip()
            if not message:
                return
            lower = message.lower()
            if any(
                k in lower
                for k in (
                    "successfully built", "successfully tagged", "writing image",
                    "error", "failed",
                )
            ):
                self.logger.info("image_build", message, progress=30)
            else:
                self.logger.info("image_build", message, progress=25)
        elif "status" in chunk:
            status = chunk.get("status")
            progress = chunk.get("progress")
            message = f"{status} {progress}".strip() if progress else status
            self.logger.info(
                "image_build", message, progress=25,
                details={"docker_status": status},
            )
        elif "error" in chunk:
            self.logger.error(
                "image_build",
                chunk.get("error") or "Docker build error",
                progress=25,
                details={"docker_build_error": chunk},
            )
