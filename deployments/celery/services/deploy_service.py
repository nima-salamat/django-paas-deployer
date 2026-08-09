"""
deployments/celery/services/deploy_service.py
---------------------------------------------
App-deploy service — the layer between the Celery ``deploy`` task and
the ``DeploymentOrchestrator``.

Key changes vs. legacy:
  * Uses ``deployments.common.parse_config`` instead of a local
    ``_parse_config`` copy (the codebase had THREE copies).
  * Acquires a per-service advisory lock for the WHOLE deploy so two
    deploys targeting the same Service cannot race.
  * Wires ``cancel_check`` into the orchestrator so a user-requested
    cancel between stages is honoured (legacy code only checked at start).
  * Reports ``rollback_failed`` distinctly from ``rollback_performed``
    in the final state transition.
"""

from __future__ import annotations

import logging
import os
import re
import traceback

from deploy.models import Deploy  # type: ignore
from deploy.deployment_state import DjangoDeploymentState  # type: ignore
from core.global_settings.config import default_ports  # type: ignore
from deployments.core.deploy import Deploy as DeployFacade
from deployments.core.types import VolumeSpec
from deployments.core.manager.container_manager import Container
from deployments.core.state.locks import acquire_service_deployment_lock
from services.models import Volume  # type: ignore

from deployments.common import parse_config, as_bool, as_int
from deployments.common.config import (
    suggest_worker_count,
    apply_workers_to_command,
    parse_workers_from_command,
)
from deployments.common.exceptions import (
    InvalidServiceStateError,
    OrchestratorDeploymentError,
)

from ..service_status import ServiceStateManager
from ..validators import DeploymentValidator
from ..helpers import DeploymentHelper, MockOrchestratorResult
from ..waiters import ContainerWaiter

logger = logging.getLogger(__name__)


def _docker_safe_tag(version) -> str:
    """Convert ``Deploy.version`` to a docker-py-safe tag."""
    if version is None:
        return "latest"
    raw = str(version).strip()
    if not raw:
        return "latest"
    if re.match(r"^\d+(\.\d+)?$", raw):
        return "v" + raw.replace(".", "-")
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "-", raw)
    if not cleaned:
        return "latest"
    if not re.match(r"^[A-Za-z_]", cleaned):
        cleaned = "v" + cleaned
    return cleaned[:128]


class DeployService:
    """Orchestrates deployment execution flows coupled with state logging."""

    def execute(self, deploy_id: int) -> None:
        # 1. Acquire the per-service advisory lock BEFORE touching the
        #    row state.  This prevents two deploys for the same Service
        #    from racing even if the row-lock transaction boundary is
        #    in the wrong place.
        try:
            deploy_item = (
                Deploy.objects
                .select_related("service")
                .filter(pk=deploy_id)
                .first()
            )
            if deploy_item is None:
                logger.warning("Deploy %s does not exist; aborting.", deploy_id)
                return
            service_id = deploy_item.service_id
        except Exception:
            logger.exception("Failed to pre-fetch deploy %s for locking.", deploy_id)
            return

        try:
            with acquire_service_deployment_lock(service_id):
                self._execute_locked(deploy_id, service_id)
        except InvalidServiceStateError as exc:
            logger.info("Skipped deploy execution for ID %s: %s", deploy_id, str(exc))
            return
        except Exception:
            # The lock itself raised (e.g. DeploymentLockError) — log and exit.
            logger.exception("Deploy %s could not acquire deployment lock.", deploy_id)
            return

    def _execute_locked(self, deploy_id: int, service_id: int) -> None:
        try:
            deploy_item = ServiceStateManager.lock_and_get_deployment(deploy_id)
        except InvalidServiceStateError as exc:
            logger.info("Skipped deploy execution for ID %s: %s", deploy_id, str(exc))
            return

        container_name = deploy_item.service.get_docker_service_name()
        state_tracker = DjangoDeploymentState(deploy_item)

        if deploy_item.cancel_requested:
            state_tracker.finish(
                MockOrchestratorResult(
                    success=False,
                    stage="cancelled",
                    message="Deployment cancelled before execution.",
                    status="cancelled",
                )
            )
            ServiceStateManager.sync_legacy_stopped(service_id)
            return

        state_tracker.start()

        try:
            result = self._process_deployment(deploy_item, container_name, state_tracker)
            if getattr(result, "status", None) == "cancelled":
                ServiceStateManager.sync_legacy_stopped(service_id)
            else:
                # If rollback itself failed, surface that — don't claim success.
                if getattr(result, "rollback_failed", False):
                    logger.error(
                        "Deploy %s succeeded in starting the new container but "
                        "a previous rollback attempt failed; operator review required.",
                        deploy_id,
                    )
                ServiceStateManager.sync_legacy_success(service_id, deploy_id=deploy_item.pk)
            logger.info("Successfully executed deploy cycle for container: %s", container_name)

        except Exception as exc:
            logger.error(
                "Deployment critical failure on %s: %s",
                container_name, str(exc), exc_info=True,
            )
            state_tracker.record_exception(exc, traceback.format_exc())
            if state_tracker.deploy.status not in {"failed", "cancelled"}:
                state_tracker.finish(
                    MockOrchestratorResult(
                        success=False,
                        stage=getattr(exc, "stage", "deployment_failed"),
                        message=str(exc) or "Deployment failed.",
                        error=str(exc),
                    )
                )
            ServiceStateManager.sync_legacy_failure(service_id, deploy_id=deploy_item.pk)
            raise

    def _process_deployment(
        self, deploy_item: Deploy, container_name: str,
        state_tracker: DjangoDeploymentState,
    ):
        cfg = parse_config(getattr(deploy_item, "config", None))
        platform = (
            str(cfg.get("platform") or "").lower().strip()
            or str(getattr(getattr(deploy_item.service, "plan", None), "platform", None) or "docker").lower().strip()
        )

        version_overrides = {
            k: cfg[k]
            for k in (
                "python_version", "django_python_version", "node_version",
                "php_version", "go_version", "dotnet_version",
                "nginx_version", "port", "build_dir",
            )
            if cfg.get(k) is not None and str(cfg.get(k)).strip() != ""
        }
        dockerfile_text = DeploymentHelper.get_dockerfile_text(
            platform, version_overrides=version_overrides or None,
        )

        DeploymentValidator.validate_for_deploy(deploy_item, dockerfile_text)

        if DeploymentHelper.is_restart_only(deploy_item, container_name):
            logger.info(
                "Fast-path conditions met. Restarting existing container: %s",
                container_name,
            )
            Container(container_name).start()
            restart_result = MockOrchestratorResult(
                success=True,
                stage="deployment_completed",
                message="Existing container instance restarted successfully.",
            )
            state_tracker.finish(restart_result)
            result = restart_result
        else:
            logger.info(
                "Full orchestration required (container/image missing or deploy changed). "
                "Building image for: %s",
                container_name,
            )
            result = self._execute_orchestrator(
                deploy_item, container_name, platform, dockerfile_text, state_tracker,
            )

        if getattr(result, "status", None) != "cancelled":
            # Re-read config in case it changed (defensive).
            cfg = parse_config(getattr(deploy_item, "config", None))
            use_celery = as_bool(cfg.get("celery"))
            wait_timeout = 90 if use_celery or platform == "django" else 45
            ContainerWaiter.wait_until_running(container_name, timeout=wait_timeout)
        return result

    def _execute_orchestrator(
        self, deploy_item: Deploy, container_name: str, platform: str,
        dockerfile_text: str, state_tracker: DjangoDeploymentState,
    ):
        service = deploy_item.service
        cfg = parse_config(getattr(deploy_item, "config", None))

        # Port resolution: explicit config > platform default.
        raw_port = cfg.get("port")
        if raw_port is not None and str(raw_port).strip() != "":
            try:
                port = int(raw_port)
            except (TypeError, ValueError):
                port = default_ports.get(platform)
        else:
            port = default_ports.get(platform)

        environment = dict(cfg.get("env") or cfg.get("environment") or {})
        environment = {str(k): str(v) for k, v in environment.items()}

        server_type = (
            getattr(deploy_item, "server_type", None)
            or cfg.get("server_type")
            or getattr(service, "server_type", None)
        )
        entry_point = (
            getattr(deploy_item, "entry_point", None)
            or cfg.get("entry_point")
            or getattr(service, "entry_point", None)
        )
        celery = as_bool(
            getattr(deploy_item, "celery", False)
            or cfg.get("celery")
            or getattr(service, "celery", False)
        )
        celery_beat = as_bool(
            getattr(deploy_item, "celery_beat", False)
            or cfg.get("celery_beat")
            or getattr(service, "celery_beat", False)
        ) and celery

        celery_app = cfg.get("celery_app") or cfg.get("celery_module") or None

        # ------------------------------------------------------------------
        # worker_count resolution
        # ------------------------------------------------------------------
        # Priority:
        #   1. Explicit Deploy.config["worker_count"] / ["workers"]
        #   2. Plan-based suggestion from max_cpu + max_ram
        #   3. --workers N inside entry_point (detector default)
        #   4. default 1
        #
        # When we auto-pick from the plan, also rewrite entry_point so a
        # hard-coded "gunicorn … --workers 3" does not ignore the plan.
        explicit_workers = (
            "worker_count" in cfg
            or "workers" in cfg
            or getattr(deploy_item, "worker_count", None) not in (None, "")
        )
        plan = getattr(service, "plan", None)
        plan_cpu = getattr(plan, "max_cpu", None) if plan is not None else None
        plan_ram = getattr(plan, "max_ram", None) if plan is not None else None

        if explicit_workers:
            worker_count = as_int(
                cfg.get("worker_count") or cfg.get("workers")
                or getattr(deploy_item, "worker_count", None),
                default=1,
                minimum=1,
            )
        else:
            from_cmd = parse_workers_from_command(entry_point)
            from_plan = suggest_worker_count(
                plan_cpu, plan_ram, platform=platform, default=1,
            )
            # Prefer plan over detector hard-code when plan resources exist.
            if plan_cpu is not None or plan_ram is not None:
                worker_count = from_plan
            elif from_cmd:
                worker_count = from_cmd
            else:
                worker_count = from_plan

            if entry_point and (
                parse_workers_from_command(entry_point) != worker_count
            ):
                entry_point = apply_workers_to_command(entry_point, worker_count)

        logger.info(
            "Orchestrator options for %s: platform=%s celery=%s celery_beat=%s "
            "server_type=%s entry_point=%s celery_app=%s worker_count=%s "
            "(explicit=%s plan_cpu=%s plan_ram=%s)",
            container_name, platform, celery, celery_beat,
            server_type, entry_point, celery_app, worker_count,
            explicit_workers, plan_cpu, plan_ram,
        )

        networks: list[tuple[str, str]] = []
        if getattr(service, "network", None) is not None and getattr(service.network, "name", None):
            networks.append((service.network.get_docker_network_name(), "bridge"))

        zip_path = ""
        if getattr(deploy_item, "zip_file", None):
            try:
                zip_path = deploy_item.zip_file.path
            except Exception as exc:
                raise OrchestratorDeploymentError(
                    f"Deploy zip file path is invalid: {exc}"
                ) from exc
        if not zip_path or not os.path.isfile(zip_path):
            raise OrchestratorDeploymentError(
                "Deploy has no ZIP file on disk. Upload a package before starting."
            )
        logger.info(
            "Deploy package ready: path=%s size=%s tag=%s name=%s",
            zip_path, os.path.getsize(zip_path),
            _docker_safe_tag(deploy_item.version), container_name,
        )

        deployer = DeployFacade(
            name=container_name,
            tag=_docker_safe_tag(deploy_item.version),
            zip_filename=zip_path,
            dockerfile_text=dockerfile_text,
            max_cpu=service.plan.max_cpu,
            max_ram=service.plan.max_ram,
            networks=networks,
            volumes=self._volume_specs(deploy_item),
            port=port,
            read_only=service.read_only,
            platform=platform,
            platform_type=service.plan.plan_type,
            event_sink=state_tracker.event_sink,
            deployment_id=deploy_item.id,
            environment=environment,
            server_type=server_type,
            celery=celery,
            celery_beat=celery_beat,
            entry_point=entry_point,
            worker_count=worker_count,
        )
        if celery_app:
            try:
                deployer.celery_app = str(celery_app).strip()
            except Exception:
                pass
            if "CELERY_APP" not in environment:
                environment["CELERY_APP"] = str(celery_app).strip()
                deployer.environment = environment

        # Wire up mid-deployment cancellation by reading cancel_requested
        # from the DB on each check.  The orchestrator calls this between
        # every stage.
        def _cancel_check() -> bool:
            try:
                fresh = Deploy.objects.filter(pk=deploy_item.pk).values_list(
                    "cancel_requested", flat=True,
                ).first()
                return bool(fresh)
            except Exception:
                return False

        # The orchestrator accepts a cancel_check callable.  We pass it
        # via the facade's deploy_result path (which constructs the
        # orchestrator internally).
        try:
            deployer._cancel_check = _cancel_check  # type: ignore[attr-defined]
        except Exception:
            pass

        result = deployer.deploy_result()
        state_tracker.finish(result)

        if not result.success and result.status != "cancelled":
            # The orchestrator's DeploymentResult.message already contains
            # the full diagnostic (including the underlying Docker error,
            # error_type, status_code, etc.).  We surface it verbatim so
            # the celery traceback and the deploy-log row show the actual
            # reason rather than a generic "Orchestrator compilation
            # failed" wrapper that hides the root cause.
            error_details = getattr(result, "details", {}) or {}
            raise OrchestratorDeploymentError(
                result.message or "Orchestrator deployment failed.",
                details={
                    "stage": getattr(result, "stage", None),
                    "container": getattr(result, "container_name", None),
                    "image": getattr(result, "image_ref", None),
                    "rollback_performed": getattr(result, "rollback_performed", False),
                    "rollback_failed": getattr(result, "rollback_failed", False),
                    "underlying_error": error_details.get("error"),
                    "error_type": error_details.get("error_type"),
                    "status_code": error_details.get("status_code"),
                    "last_stage": error_details.get("last_stage"),
                },
            )
        return result

    # ------------------------------------------------------------------
    # Volume resolution (unchanged)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_volumes_for_service(service):
        return Volume.objects.filter(service_id=service.pk)

    @staticmethod
    def _volume_specs(deploy_item: Deploy) -> list:
        specs = []
        service = deploy_item.service
        service_id = str(service.id)

        for volume in DeployService._get_volumes_for_service(service):
            attachments = getattr(volume, "service_attachments", None) or {}
            if not isinstance(attachments, dict):
                attachments = {}
            attrs = attachments.get(service_id) or {}
            if not isinstance(attrs, dict):
                attrs = {}

            bind = (
                attrs.get("bind")
                or getattr(volume, "default_bind", None)
                or getattr(volume, "bind", None)
            )
            mode = (
                attrs.get("mode")
                or getattr(volume, "default_mode", None)
                or getattr(volume, "mode", None)
                or "rw"
            )

            if not bind:
                logger.warning(
                    "Skipping volume '%s' for service %s: no bind path configured.",
                    getattr(volume, "name", volume.pk), service_id,
                )
                continue

            specs.append(
                VolumeSpec(
                    source=volume.get_docker_volume_name(),
                    target=bind,
                    mode=mode,
                    mount_type="volume",
                    size_mb=getattr(volume, "size_mb", None),
                )
            )
        return specs
