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
from deployments.common.deployment_profile import normalize_profile
from deployments.common.resource_policy import runtime_limits, worker_count as derive_worker_count, build_limits
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


def _docker_tag_from_deploy(version) -> str:
    """Return the Deploy.version value unchanged as the Docker tag.

    Deploy.version is the canonical server-side version field.  Do not invent
    staging tags or rewrite the value here; the Image manager validates the
    final reference before sending it to Docker.
    """
    if version is None:
        return "latest"
    value = str(version).strip()
    return value or "latest"

# Backward-compatible symbol for older internal callers/tests. It does not
# transform the version; it returns the model value unchanged.
_docker_safe_tag = _docker_tag_from_deploy



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

        started = state_tracker.start()
        if started is False:
            ServiceStateManager.sync_legacy_stopped(service_id)
            return

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
        cfg = normalize_profile(
            parse_config(getattr(deploy_item, "config", None)),
            plan_cpu=getattr(getattr(deploy_item.service, "plan", None), "max_cpu", None),
            plan_ram_mb=getattr(getattr(deploy_item.service, "plan", None), "max_ram", None),
        )
        # Accept both the modern nested config and legacy flat keys.
        build_options = dict(cfg.get("build_options") or {})
        for _k in ("build_command", "install_command", "package_manager", "build_dir", "build_target", "build_args", "build_network", "no_cache", "pull"):
            if _k in cfg and _k not in build_options:
                build_options[_k] = cfg[_k]
        runtime_options = dict(cfg.get("runtime_options") or {})
        plan = getattr(deploy_item.service, "plan", None)
        resource_limits = runtime_limits(plan)
        for legacy_key in ("build_args", "buildargs", "build_target", "build_network", "no_cache", "pull"):
            if legacy_key in cfg and legacy_key not in build_options:
                mapped = {"build_target": "target", "build_network": "network", "no_cache": "no_cache", "pull": "pull", "build_args": "build_args", "buildargs": "build_args"}[legacy_key]
                build_options[mapped] = cfg[legacy_key]

        # Plan controls the execution family; config may only refine a
        # framework within that family (e.g. Laravel on a PHP plan).
        plan_platform = str(getattr(getattr(deploy_item.service, "plan", None), "platform", None) or "docker").lower().strip()
        requested_platform = str(cfg.get("platform") or "").lower().strip()
        platform = plan_platform
        # Normalize framework aliases so Laravel never falls through as plain "php".
        # plan.platform may still be "php" while Deploy.config / detection says laravel.
        _fw = str(cfg.get("framework") or cfg.get("framework_name") or "").lower().strip()
        if platform == "php" and _fw in ("laravel", "lumen", "symfony", "codeigniter"):
            platform = _fw
        if platform == "php" and str(cfg.get("laravel") or "").lower() in ("1", "true", "yes"):
            platform = "laravel"
        # Persist so DockerfileGenerator / _render_php see platform=laravel
        if platform in ("laravel", "lumen", "symfony", "codeigniter"):
            cfg["platform"] = platform
            try:
                # Best-effort: keep Deploy.config in sync for later stages
                if hasattr(deploy_item, "config"):
                    import json as _json
                    raw_cfg = getattr(deploy_item, "config", None)
                    if isinstance(raw_cfg, dict):
                        raw_cfg = {**raw_cfg, "platform": platform}
                        deploy_item.config = raw_cfg
                    elif isinstance(raw_cfg, str) and raw_cfg.strip():
                        try:
                            parsed = _json.loads(raw_cfg)
                            if isinstance(parsed, dict):
                                parsed["platform"] = platform
                                deploy_item.config = _json.dumps(parsed)
                        except Exception:
                            pass
            except Exception:
                pass

        # Explicit config always wins over detector output.
        detected_project_cfg = runtime_options.get("project_cfg") or {}
        build_command = cfg.get("build_command") or detected_project_cfg.get("build_command")
        install_command = cfg.get("install_command") or detected_project_cfg.get("install_command")
        build_dir = cfg.get("build_dir") or detected_project_cfg.get("build_dir")

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
        cfg = normalize_profile(
            parse_config(getattr(deploy_item, "config", None)),
            plan_cpu=getattr(getattr(service, "plan", None), "max_cpu", None),
            plan_ram_mb=getattr(getattr(service, "plan", None), "max_ram", None),
        )
        build_options = dict(cfg.get("build_options") or {})
        runtime_options = dict(cfg.get("runtime_options") or {})
        plan_cpu = getattr(getattr(service, "plan", None), "max_cpu", None)
        plan_ram = getattr(getattr(service, "plan", None), "max_ram", None)
        resource_limits = runtime_limits(service.plan)
        build_resource_policy = build_limits(service.plan)
        detected_project_cfg = runtime_options.get("project_cfg") or {}
        build_command = cfg.get("build_command") or build_options.get("build_command") or detected_project_cfg.get("build_command")
        install_command = cfg.get("install_command") or build_options.get("install_command") or detected_project_cfg.get("install_command")
        build_dir = cfg.get("build_dir") or build_options.get("build_dir") or detected_project_cfg.get("build_dir")
        package_manager = cfg.get("package_manager") or build_options.get("package_manager") or detected_project_cfg.get("package_manager")

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

        # Laravel/PHP defaults when root FS may be read-only: app reads these
        # from the process environment even without a writable .env file.
        if platform in ("laravel", "php", "lumen", "symfony"):
            environment.setdefault("LOG_CHANNEL", "stderr")
            environment.setdefault("SESSION_DRIVER", "file")
            environment.setdefault("CACHE_STORE", "file")
            environment.setdefault("CACHE_DRIVER", "file")
            environment.setdefault("QUEUE_CONNECTION", "sync")
            if not environment.get("APP_KEY"):
                # Generate a stable-enough key for this deploy so encryption works.
                # Prefer value from deploy config if the user set one later.
                import base64
                import os as _os

                environment["APP_KEY"] = "base64:" + base64.b64encode(
                    _os.urandom(32)
                ).decode("ascii")
            environment.setdefault("APP_ENV", "production")

            db_conn = (
                environment.get("DB_CONNECTION")
                or cfg.get("db_connection")
                or cfg.get("database")
                or cfg.get("DB_CONNECTION")
                or ""
            )
            db_conn = str(db_conn).strip().lower()
            if not db_conn:
                db_conn = "sqlite"
            environment["DB_CONNECTION"] = db_conn
            if db_conn == "sqlite":
                environment.setdefault(
                    "DB_DATABASE", "/var/www/html/database/database.sqlite"
                )
                environment.setdefault("SESSION_DRIVER", "file")
                environment.setdefault("CACHE_STORE", "file")

            fb = (
                cfg.get("front_build_platform")
                or cfg.get("frontend")
                or cfg.get("frontend_build")
                or environment.get("FRONT_BUILD_PLATFORM")
                or ""
            )
            if fb:
                environment["FRONT_BUILD_PLATFORM"] = str(fb).strip().lower()

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
        # worker_count is server-owned. Tenant config is ignored.
        # ------------------------------------------------------------------
        explicit_workers = False
        worker_count = derive_worker_count(service.plan)

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
            _docker_tag_from_deploy(deploy_item.version), container_name,
        )

        deployer = DeployFacade(
            name=container_name,
            tag=_docker_tag_from_deploy(deploy_item.version),
            zip_filename=zip_path,
            dockerfile_text=dockerfile_text,
            max_cpu=resource_limits["cpu"],
            max_ram=resource_limits["memory_mb"],
            networks=networks,
            volumes=self._volume_specs(deploy_item, platform=platform),
            port=port,
            # Laravel/PHP need writable storage even when service.read_only
            # is True (root FS RO).  Named volumes cover storage paths.
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
            resource_limits=resource_limits,
            build_resource_policy=build_resource_policy,
            build_options={**build_options, "build_command": build_command, "install_command": install_command, "build_dir": build_dir, "package_manager": package_manager},
            runtime_options=runtime_options,
            labels={"deployment.id": str(deploy_item.pk), "service.id": str(service.pk)},
            runtime_version=cfg.get("runtime_version") or cfg.get("node_version") or cfg.get("php_version"),
            package_manager=package_manager,
            working_directory=cfg.get("working_directory") or runtime_options.get("working_directory") or "/app",
            build_dir=build_dir,
            install_command=install_command,
            build_command=build_command,
            start_command=cfg.get("start_command"),
            frontend=dict(cfg.get("frontend") or {}),
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

    # Laravel/PHP writable paths that must be volumes when root FS is RO.
    _LARAVEL_DEFAULT_VOLUMES = (
        ("storage", "/var/www/html/storage", 512),
        ("bootstrap-cache", "/var/www/html/bootstrap/cache", 128),
    )
    _LARAVEL_SQLITE_VOLUME = ("database", "/var/www/html/database", 256)

    @classmethod
    def _ensure_laravel_volumes(
        cls, service, platform: str, *, db_connection: str | None = None
    ) -> None:
        """
        Auto-create storage / bootstrap-cache (+ database for sqlite).
        """
        p = (platform or "").lower().strip()
        if p not in ("laravel", "php", "lumen", "symfony"):
            return
        wanted = list(cls._LARAVEL_DEFAULT_VOLUMES)
        dbc = (db_connection or "").strip().lower()
        if dbc in ("", "sqlite"):
            wanted.append(cls._LARAVEL_SQLITE_VOLUME)

        existing = list(cls._get_volumes_for_service(service))
        existing_binds = set()
        for vol in existing:
            att = (vol.service_attachments or {}).get(str(service.id)) or {}
            bind = att.get("bind") or getattr(vol, "default_bind", "") or ""
            if bind:
                existing_binds.add(bind.rstrip("/"))

        for short, bind, size_mb in wanted:
            if bind.rstrip("/") in existing_binds:
                continue
            # Unique volume name within 32 chars
            try:
                sid = service.id.hex[:6]
            except Exception:
                sid = str(service.pk)[:6]
            name = f"lv-{sid}-{short}"[:32]
            # Quota: skip if plan cannot allocate
            try:
                ok, msg = service.can_allocate_storage(size_mb)
                if not ok:
                    logger.warning(
                        "Skip auto volume %s for service %s: %s",
                        name, service.pk, msg,
                    )
                    continue
            except Exception as exc:
                logger.warning("quota check failed for auto volume: %s", exc)
                continue
            try:
                vol = Volume.objects.create(
                    name=name,
                    user_id=service.user_id,
                    service=service,
                    service_attachments={
                        str(service.id): {
                            "bind": bind,
                            "mode": "rw",
                        }
                    },
                    default_bind=bind,
                    default_mode="rw",
                    size_mb=size_mb,
                )
                logger.info(
                    "Auto-created Laravel volume %s → %s (%s MB) for service %s",
                    vol.name, bind, size_mb, service.pk,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to auto-create volume %s for service %s: %s",
                    name, service.pk, exc,
                )

    @staticmethod
    def _volume_specs(deploy_item: Deploy, platform: str | None = None) -> list:
        service = deploy_item.service
        service_id = str(service.id)

        # Ensure Laravel writable paths exist as named volumes
        try:
            cfg = {}
            raw = getattr(deploy_item, "config", None)
            if isinstance(raw, dict):
                cfg = raw
            elif isinstance(raw, str) and raw.strip():
                import json as _json
                try:
                    cfg = _json.loads(raw) or {}
                except Exception:
                    cfg = {}
            plat = (platform or str(cfg.get("platform") or "")).lower()
            cfg_db = ""
            env_cfg = cfg.get("env") or cfg.get("environment") or {}
            if isinstance(env_cfg, dict):
                cfg_db = str(env_cfg.get("DB_CONNECTION") or "")
            cfg_db = cfg_db or str(
                cfg.get("db_connection") or cfg.get("database") or ""
            )
            DeployService._ensure_laravel_volumes(
                service, plat, db_connection=cfg_db
            )
        except Exception as exc:
            logger.warning("ensure_laravel_volumes failed: %s", exc)

        specs = []
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
