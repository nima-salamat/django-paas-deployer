"""Django application boundary for deployment execution.

The normal Swarm path composes immutable revision state into a native
DeploymentPlan and delegates sequencing to DeploymentLifecycleExecutor and
RuntimeContract. The legacy Deploy facade remains only for explicit
non-Swarm compatibility execution.
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
from deployments.core.types import EndpointSpec, NetworkSpec, VolumeSpec
from deployments.core.runtime_graph import ServiceRuntimeGraph
from deployments.core.manager.container_manager import Container
from deployments.core.swarm import swarm_enabled
from deployments.core.state.locks import acquire_service_deployment_lock
from deployments.core.state.manager import StateManager
from services.models import Volume  # type: ignore
from services.revisioning import ensure_revision_for_deploy, activate_revision_locked, materialize_revision_config, mark_revision_failed

from deployments.common import parse_config, as_bool, as_int
from deployments.common.docker_identity import canonical_image_ref, canonical_image_tag
from deployments.common.deadline import DeploymentDeadline
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
    DeploymentValidationError,
    DeploymentCancelled,
    to_deployment_error,
)
from deployments.planning import ConfigurationResolver, DeploymentPlanCompiler
from deployments.application.context import DeploymentExecutionContext, DeploymentExecutionEvent
from deployments.application.lifecycle import DeploymentLifecycleExecutor
from deployments.application.strategies import CallbackDeploymentStrategy
from deployments.infrastructure.django_lifecycle import DjangoDeploymentLifecycleStore
from deployments.core.dockerfile import DockerfileGenerator
from deployments.core.converter import convert_zip_to_tar
from deployments.core.types import DeploymentConfig, DeploymentEvent
from deployments.planning.runtime_spec import RuntimeSpec
from deployments.planning.policies import ReleaseSpec
from deployments.runtime import RuntimeBackend, RuntimeIdentity
from deployments.infrastructure.django_runtime import DjangoRuntimeSelectionResolver
from deployments.runtime.errors import RuntimeUnavailableError

from ..service_status import ServiceStateManager
from ..validators import DeploymentValidator
from ..helpers import DeploymentHelper, MockOrchestratorResult

logger = logging.getLogger(__name__)


def _docker_tag_from_deploy(version) -> str:
    """Resolve the canonical Docker image tag for a Deploy.version value."""
    return canonical_image_tag(version)



# Backward-compatible symbol for older internal callers/tests. It does not
# transform the version; it returns the model value unchanged.
_docker_safe_tag = _docker_tag_from_deploy



class DeployService:
    """Orchestrates deployment execution flows coupled with state logging."""

    def execute(self, deploy_id: int, *, task_id: str | None = None) -> None:
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
                self._execute_locked(deploy_id, service_id, task_id=task_id)
        except InvalidServiceStateError as exc:
            logger.info("Skipped deploy execution for ID %s: %s", deploy_id, str(exc))
            return
        except Exception as exc:
            # Do not turn a deterministic deployment bug into an invisible
            # worker-side log.  DeploymentError instances retain their retry
            # classification; unexpected exceptions are translated to a
            # non-recoverable internal platform error for the Celery boundary.
            translated = to_deployment_error(exc, stage="deployment_lock")
            logger.exception(
                "Deploy %s could not complete its deployment lock boundary: %s",
                deploy_id, translated.technical_message,
            )
            raise translated from exc

    def _execute_locked(self, deploy_id: int, service_id: int, *, task_id: str | None = None) -> None:
        try:
            deploy_item = ServiceStateManager.lock_and_get_deployment(deploy_id, task_id=task_id)
        except InvalidServiceStateError as exc:
            logger.info("Skipped deploy execution for ID %s: %s", deploy_id, str(exc))
            return

        # Preserve the lifecycle intent recorded by the caller. A Stop request
        # may have advanced lifecycle_generation while this worker was waiting.
        # Capture the service lifecycle generation at execution start.
        # intents bump this generation and invalidate an in-flight deployment.
        expected_lifecycle_generation = int(
            getattr(deploy_item.service, "lifecycle_generation", 0) or 0
        )
        container_name = deploy_item.service.get_docker_service_name()
        state_tracker = DjangoDeploymentState(deploy_item)
        StateManager.heartbeat_deploy(deploy_item.pk, task_id=task_id, stage="starting")

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
            StateManager.heartbeat_deploy(deploy_item.pk, task_id=task_id, stage="preparing")

            # A deployment executes an immutable ServiceRevision snapshot.
            # Keep Deploy.config as a compatibility input during migration,
            # but stop treating it as the runtime source of truth.
            deploy_item = ensure_revision_for_deploy(deploy_item)
            deploy_item.refresh_from_db(fields=["revision"])
            if deploy_item.revision_id is None:
                raise DeploymentValidationError(
                    "Deployment could not create a service revision snapshot.",
                    stage="revision",
                    user_message="The deployment configuration could not be snapshotted.",
                )

            previous_deploy_id = getattr(deploy_item, "previous_deploy_id", None)
            def _activate_deployment() -> None:
                from django.db import transaction
                from services.lifecycle.authority import get_authoritative_deploy
                from django.utils import timezone
                from services.models import Service

                with transaction.atomic():
                    service = Service.objects.select_for_update().get(pk=service_id)
                    current_deploy = Deploy.objects.select_for_update().get(pk=deploy_item.pk)
                    if current_deploy.cancel_requested or str(current_deploy.status).lower() == "cancelled":
                        raise DeploymentCancelled(
                            "Deployment cancellation was requested before activation.",
                            stage="cancelled",
                            user_message="Deployment was cancelled before activation.",
                            details={"deploy_id": deploy_item.pk, "service_id": service_id},
                        )

                    actual_lifecycle_generation = int(
                        getattr(service, "lifecycle_generation", 0) or 0
                    )
                    if actual_lifecycle_generation != expected_lifecycle_generation:
                        raise InvalidServiceStateError(
                            "Service lifecycle changed while this deployment was preparing to activate.",
                            details={
                                "expected_lifecycle_generation": expected_lifecycle_generation,
                                "actual_lifecycle_generation": actual_lifecycle_generation,
                                "service_id": service_id,
                            },
                        )

                    # Activation is idempotent for the same immutable revision.
                    # A duplicate delivery or a recovery path may have already
                    # committed this exact revision. That is not a conflicting
                    # deployment and must not turn a successful Swarm rollout
                    # into a false failure.
                    if str(service.active_revision_id or "") == str(deploy_item.revision_id):
                        Service.objects.filter(pk=service_id).update(
                            desired_state="running",
                        )
                        logger.info(
                            "Activation already committed for deploy=%s revision=%s service=%s.",
                            deploy_item.pk, deploy_item.revision_id, service_id,
                        )
                        return

                    # Use the authoritative active_revision pointer only.
                    # Do not call the legacy get_active_deploy() bridge here:
                    # it can mutate active_revision while merely resolving
                    # selected_deploy, which makes the concurrency fence report
                    # a change that was not an actual competing activation.
                    active_deploy = get_authoritative_deploy(service)
                    current = active_deploy.pk if active_deploy else None
                    if current != previous_deploy_id:
                        raise InvalidServiceStateError(
                            "Active revision changed while this deployment was preparing to activate.",
                            details={
                                "expected_previous_deploy": previous_deploy_id,
                                "actual_active_deploy": current,
                                "actual_active_revision": str(service.active_revision_id or ""),
                                "deploy_revision": str(deploy_item.revision_id or ""),
                            },
                        )

                    activate_revision_locked(service, deploy_item.revision_id)
                    Service.objects.filter(pk=service_id).update(
                        desired_state="running",
                    )

                logger.info(
                    "Activated deploy=%s revision=%s for service=%s",
                    deploy_item.pk, deploy_item.revision_id, service_id,
                )

            result = self._process_deployment(
                deploy_item, container_name, state_tracker, task_id=task_id,
                activation_callback=_activate_deployment,
            )
            if deploy_item.revision_id and getattr(result, "status", None) in {"failed", "cancelled"}:
                mark_revision_failed(deploy_item.revision_id)
            # Synchronize legacy Service state only from the deployment state
            # that was actually committed. A stale worker must not mark the
            # service RUNNING after another deployment has won activation.
            final = Deploy.objects.select_related("service").filter(pk=deploy_item.pk).values(
                "status", "service__active_revision_id"
            ).first()
            if not final:
                logger.warning("Deploy %s disappeared before final service sync.", deploy_id)
                return
            final_status = final.get("status")
            active_revision_id = final.get("service__active_revision_id")
            if final_status == "cancelled":
                ServiceStateManager.sync_legacy_stopped(service_id)
            elif (
                final_status == "succeeded"
                and str(active_revision_id or "") == str(deploy_item.revision_id)
            ):
                # If rollback itself failed, surface that — don't claim success.
                if getattr(result, "rollback_failed", False):
                    logger.error(
                        "Deploy %s succeeded in starting the new container but "
                        "a previous rollback attempt failed; operator review required.",
                        deploy_id,
                    )
                ServiceStateManager.sync_legacy_success(service_id, deploy_id=deploy_item.pk)
            elif final_status == "failed":
                ServiceStateManager.sync_legacy_failure(service_id, deploy_id=deploy_item.pk)
            else:
                logger.info(
                    "Skipping legacy service sync for deploy=%s status=%s active_revision=%s; "
                    "worker may be stale or another deployment may be authoritative.",
                    deploy_id, final_status, active_revision_id,
                )
            logger.info("Completed deploy cycle for container: %s", container_name)

        except Exception as exc:
            traceback_text = traceback.format_exc()
            translated = to_deployment_error(
                exc,
                stage=getattr(exc, "stage", None) or "deployment",
            )
            if getattr(deploy_item, "revision_id", None):
                try:
                    mark_revision_failed(deploy_item.revision_id)
                except Exception:
                    logger.exception("Failed to mark revision %s as failed", deploy_item.revision_id)
            logger.error(
                "Deployment critical failure on %s: code=%s stage=%s technical=%s",
                container_name,
                translated.code,
                translated.stage,
                translated.technical_message,
                exc_info=True,
            )
            try:
                from deployments.observability import capture_exception
                capture_exception(
                    exc,
                    tags={
                        "deployment_id": str(deploy_item.pk),
                        "service_id": str(service_id),
                        "revision_id": str(getattr(deploy_item, "revision_id", "") or ""),
                        "task_id": str(task_id or ""),
                        "stage": translated.stage,
                        "error_code": translated.code,
                        "error_category": translated.category,
                    },
                    context={"failure": translated.failure_metadata},
                )
            except Exception:
                logger.debug("Sentry deployment diagnostics unavailable.", exc_info=True)

            # A lower layer may already have produced a terminal result (for
            # example _process_deployment raises after orchestrator.finish()).
            # In that case persist diagnostics silently and DO NOT emit another
            # user-facing terminal failure event.
            if state_tracker.deploy.status in {"failed", "cancelled"}:
                state_tracker.record_exception(translated, traceback_text)
            else:
                state_tracker.finish(
                    MockOrchestratorResult(
                        success=False,
                        stage=translated.stage,
                        message=translated.user_message,
                        error=translated.technical_message,
                    ),
                    exception=translated,
                    traceback_text=traceback_text,
                )
            ServiceStateManager.sync_legacy_failure(service_id, deploy_id=deploy_item.pk)
            raise translated from exc

    def _process_deployment(
        self, deploy_item: Deploy, container_name: str,
        state_tracker: DjangoDeploymentState,
        *,
        task_id: str | None = None,
        activation_callback=None,
    ):
        # Revision is now the executable source of truth. Deploy.config remains
        # only the compatibility input used when the revision is first created.
        revision_config = (
            materialize_revision_config(deploy_item.revision)
            if getattr(deploy_item, "revision_id", None)
            else None
        )
        cfg = normalize_profile(
            parse_config(
                revision_config
                if isinstance(revision_config, dict)
                else getattr(deploy_item, "config", None)
            ),
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

        # Docker platform is source-driven: a tenant Dockerfile or single-service
        # Compose file is inspected and normalized before any Docker build starts.
        # Never execute docker compose itself and never import host paths from it.
        docker_source_resolution = None
        if platform == "docker" and getattr(deploy_item, "zip_file", None):
            inspect_dir = None
            try:
                archive_path = deploy_item.zip_file.path
                from deployments.core.platform_bridge import extract_zip_to_temp
                from deployments.core.docker_source import inspect_docker_source
                inspect_dir, docker_root = extract_zip_to_temp(archive_path)
                docker_source_resolution = inspect_docker_source(
                    docker_root,
                    environment=dict(cfg.get("env") or cfg.get("environment") or {}),
                )
            except DeploymentValidationError:
                raise
            except Exception as exc:
                raise DeploymentValidationError(
                    "Docker source security validation failed.",
                    stage="docker_source_validation",
                    details={"technical_error": str(exc)},
                ) from exc
            finally:
                if inspect_dir:
                    import shutil as _shutil
                    _shutil.rmtree(inspect_dir, ignore_errors=True)

            report = docker_source_resolution.report()
            cfg["docker_source_report"] = report
            cfg["docker_source_runtime"] = dict(docker_source_resolution.runtime or {})
            cfg["docker_source_volumes"] = list(docker_source_resolution.volumes or [])
            if docker_source_resolution.blocked:
                raise DeploymentValidationError(
                    "The supplied Docker source contains operations that PassDeployer does not allow.",
                    stage="docker_source_validation",
                    details=report,
                )
            for finding in docker_source_resolution.findings:
                if finding.action == "strip":
                    logger.warning(
                        "Docker source policy stripped %s from %s: %s",
                        finding.code, finding.path or "source", finding.message,
                    )
                elif finding.action == "warn":
                    logger.warning(
                        "Docker source policy warning %s in %s: %s",
                        finding.code, finding.path or "source", finding.message,
                    )
            logger.info(
                "Docker source accepted: kind=%s file=%s findings=%d volumes=%d",
                docker_source_resolution.source_kind,
                docker_source_resolution.source_file,
                len(docker_source_resolution.findings),
                len(docker_source_resolution.volumes),
            )
            # Current execution uses the normalized Dockerfile as the sole build
            # input; Compose is only the declarative source for runtime options.
            dockerfile_text = docker_source_resolution.dockerfile_text
            docker_runtime = docker_source_resolution.runtime or {}
            compose_env = dict(docker_runtime.get("environment") or {})
            explicit_env = dict(cfg.get("env") or cfg.get("environment") or {})
            cfg["environment"] = {**compose_env, **explicit_env}
            cfg["env"] = dict(cfg["environment"])
            source_build_args = dict(docker_runtime.get("build_args") or {})
            if source_build_args:
                cfg["build_options"] = {
                    **dict(cfg.get("build_options") or {}),
                    "build_args": {
                        **source_build_args,
                        **dict((cfg.get("build_options") or {}).get("build_args") or {}),
                    },
                }
            if "read_only" in docker_runtime:
                cfg.setdefault("runtime_options", {})["read_only"] = bool(docker_runtime.get("read_only"))
            if "restart_policy" in docker_runtime:
                cfg.setdefault("runtime_options", {})["restart_policy"] = dict(
                    docker_runtime.get("restart_policy") or {}
                )
            if docker_runtime.get("working_directory"):
                cfg["working_directory"] = str(docker_runtime["working_directory"])
            if docker_runtime.get("port"):
                cfg["port"] = int(docker_runtime["port"])
            if docker_runtime.get("public") and docker_runtime.get("port"):
                cfg["docker_source_public"] = True
            command = docker_runtime.get("entrypoint") or docker_runtime.get("command")
            if docker_runtime.get("entrypoint") and docker_runtime.get("command"):
                command = f"{docker_runtime['entrypoint']} {docker_runtime['command']}".strip()
            if command:
                cfg["start_command"] = str(command)
            if docker_runtime.get("healthcheck_path"):
                cfg["healthcheck_path"] = str(docker_runtime["healthcheck_path"])
            if docker_runtime.get("healthcheck_timeout"):
                cfg["healthcheck_timeout"] = float(docker_runtime["healthcheck_timeout"])
            if docker_runtime.get("labels"):
                cfg["labels"] = {
                    **dict(docker_runtime.get("labels") or {}),
                    **dict(cfg.get("labels") or {}),
                }
            cfg["source_kind"] = docker_source_resolution.source_kind
            cfg.setdefault("build_options", {})["secure_docker_source"] = True
            # Keep the normalized result on the in-memory Deploy compatibility
            # object so volume resolution later in this same execution sees it.
            try:
                raw_cfg = dict(deploy_item.config or {}) if isinstance(deploy_item.config, dict) else {}
                raw_cfg.update({
                    "source_kind": docker_source_resolution.source_kind,
                    "docker_source_report": report,
                    "docker_source_runtime": dict(docker_source_resolution.runtime or {}),
                    "docker_source_volumes": list(docker_source_resolution.volumes or []),
                })
                deploy_item.config = raw_cfg
            except Exception:
                pass

        # Explicit config always wins over detector output.
        detected_project_cfg = runtime_options.get("project_cfg") or {}
        build_command = cfg.get("build_command") or detected_project_cfg.get("build_command")
        install_command = cfg.get("install_command") or detected_project_cfg.get("install_command")
        paths_cfg = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}
        # Resolve legacy nested path configuration once and keep the resolved
        # value on the orchestration config.  Downstream methods receive this
        # same config rather than reaching into a caller's local variables.
        cfg["resolved_paths"] = dict(paths_cfg)
        build_dir = cfg.get("build_dir") or paths_cfg.get("build_dir") or detected_project_cfg.get("build_dir")

        # Validate scoped tenant customizations without disabling the rest of
        # automatic detection. Path/URL overrides are isolated to their
        # corresponding renderer and unsafe/nonexistent project paths fail
        # before Docker build.
        try:
            from deployments.common.config import validate_platform_config
            _platform_report = validate_platform_config(getattr(deploy_item, "config", None), platform)
            for _warning in _platform_report.get("warnings") or []:
                logger.warning("Platform config warning for %s: %s", container_name, _warning)
        except ValueError as exc:
            raise OrchestratorDeploymentError(str(exc)) from exc

        version_overrides = {
            k: cfg[k]
            for k in (
                "python_version", "django_python_version", "node_version",
                "php_version", "go_version", "dotnet_version",
                "nginx_version", "port", "build_dir",
            )
            if cfg.get(k) is not None and str(cfg.get(k)).strip() != ""
        }
        if docker_source_resolution is not None:
            # Secure Docker source inspection above already selected and
            # validated the tenant Dockerfile / Compose build input.
            pass
        elif str(cfg.get("dockerfile_source") or "").strip().lower() == "archive":
            try:
                archive_path = deploy_item.zip_file.path if getattr(deploy_item, "zip_file", None) else ""
                dockerfile_text = DeploymentHelper.get_dockerfile_from_archive(archive_path)
            except Exception as exc:
                raise DeploymentValidationError(
                    "The supplied deployment package has an invalid Dockerfile.",
                    details={"technical_error": str(exc)},
                    stage="validation",
                ) from exc
        else:
            dockerfile_text = DeploymentHelper.get_dockerfile_text(
                platform, version_overrides=version_overrides or None,
            )

        DeploymentValidator.validate_for_deploy(deploy_item, dockerfile_text)

        if not swarm_enabled() and DeploymentHelper.is_restart_only(deploy_item, container_name):
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
                cfg=cfg, activation_callback=activation_callback,
            )

        return result

    def _execute_orchestrator(
        self, deploy_item: Deploy, container_name: str, platform: str,
        dockerfile_text: str, state_tracker: DjangoDeploymentState,
        *, cfg: dict, activation_callback=None,
    ):
        service = deploy_item.service
        # cfg is resolved by _process_deployment and explicitly handed to this
        # stage.  Re-parsing Deploy.config here was the source of hidden
        # configuration coupling and allowed path state to escape its scope.
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

        healthcheck_path = cfg.get("healthcheck_path") or runtime_options.get("healthcheck_path")
        expected_status = cfg.get("healthcheck_expected_status") or runtime_options.get("healthcheck_expected_status") or (200, 204)
        healthcheck_timeout = cfg.get("healthcheck_timeout") or runtime_options.get("healthcheck_timeout") or 5.0

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
        build_environment = {
            str(k): str(v)
            for k, v in dict(cfg.get("build_env") or {}).items()
        }

        # The revision is the normalized runtime graph boundary. Legacy
        # profile keys are still accepted, but endpoint publication,
        # processes, networks and environment are derived from the graph.
        runtime_graph = (
            ServiceRuntimeGraph.from_revision(deploy_item.revision)
            if getattr(deploy_item, "revision_id", None)
            else None
        )
        if runtime_graph is not None:
            environment = dict(runtime_graph.runtime_environment)
            build_environment.update(runtime_graph.build_environment)
            cfg["processes"] = [
                {
                    "name": process.name,
                    "process_type": process.process_type,
                    "command": process.command,
                    "entrypoint": process.entrypoint,
                    "replicas": process.replicas,
                    "enabled": process.enabled,
                }
                for process in runtime_graph.processes
            ]
            cfg["endpoints"] = runtime_graph.public_endpoints()
            runtime_options["processes"] = [
                {
                    "name": process.name,
                    "process_type": process.process_type,
                    "command": process.command,
                    "entrypoint": process.entrypoint,
                    "replicas": process.replicas,
                    "enabled": process.enabled,
                    "environment": process.environment,
                }
                for process in runtime_graph.processes
            ]
            if runtime_graph.networks:
                cfg["networks"] = list(runtime_graph.networks)
            runtime_options.setdefault("exposed_ports", runtime_graph.exposed_ports())
            runtime_options.setdefault("port_bindings", runtime_graph.port_bindings())
            runtime_options["public_endpoints"] = runtime_graph.public_endpoints()
            primary_endpoint = runtime_graph.primary_public_endpoint()
            if primary_endpoint is not None:
                port = primary_endpoint.target_port
                if primary_endpoint.hostname:
                    cfg["public_host"] = primary_endpoint.hostname


        # Docker-source runtime metadata intentionally overrides the stale
        # revision graph for this source kind. The immutable revision still
        # carries the original service intent, while the uploaded Docker
        # source is the authority for its own Compose runtime semantics.
        docker_runtime_source = cfg.get("docker_source_runtime") or {}
        if platform == "docker" and docker_runtime_source:
            source_environment = {
                str(k): str(v)
                for k, v in dict(docker_runtime_source.get("environment") or {}).items()
            }
            explicit_environment = {
                str(k): str(v)
                for k, v in dict(cfg.get("env") or cfg.get("environment") or {}).items()
            }
            environment = {**source_environment, **explicit_environment}
            cfg["environment"] = dict(environment)
            if docker_runtime_source.get("read_only"):
                runtime_options["read_only"] = True
            if docker_runtime_source.get("working_directory"):
                runtime_options["working_directory"] = str(docker_runtime_source["working_directory"])
            if docker_runtime_source.get("port"):
                port = int(docker_runtime_source["port"])
            if docker_runtime_source.get("healthcheck_path"):
                healthcheck_path = str(docker_runtime_source["healthcheck_path"])
            if docker_runtime_source.get("healthcheck_timeout"):
                healthcheck_timeout = float(docker_runtime_source["healthcheck_timeout"])
            command = docker_runtime_source.get("entrypoint") or docker_runtime_source.get("command")
            if docker_runtime_source.get("entrypoint") and docker_runtime_source.get("command"):
                command = f"{docker_runtime_source['entrypoint']} {docker_runtime_source['command']}".strip()
            if command:
                cfg["start_command"] = str(command)
            runtime_options["docker_source_labels"] = dict(docker_runtime_source.get("labels") or {})
            if docker_runtime_source.get("public") and docker_runtime_source.get("port"):
                runtime_options["docker_source_public"] = True
            cfg["runtime_options"] = runtime_options


        # URL handling is intentionally scoped: it can change the public/asset
        # URL policy without disabling platform detection, builds or static
        # serving. Explicit environment values always win.
        url_handling = dict(cfg.get("url_handling") or {}) if isinstance(cfg.get("url_handling"), dict) else {}
        url_mode = str(url_handling.get("mode") or "auto").strip().lower()
        try:
            from core import settings_service as _core_settings
            if not _core_settings.auto_public_url_handling() and url_mode == "auto":
                url_mode = "disabled"
        except Exception:
            pass
        if url_mode not in {"auto", "disabled", "custom"}:
            raise OrchestratorDeploymentError(
                "Invalid url_handling.mode; expected auto, disabled, or custom."
            )
        custom_public_url = str(
            url_handling.get("public_url") or cfg.get("public_url") or ""
        ).strip()
        custom_asset_url = str(
            url_handling.get("asset_url") or cfg.get("asset_url") or ""
        ).strip()
        if url_mode == "custom":
            import re as _re
            for _label, _value in (("public_url", custom_public_url), ("asset_url", custom_asset_url)):
                if _value and not _re.match(r"^https?://[^\s'\"`;&|<>]+/?$", _value):
                    raise OrchestratorDeploymentError(f"Invalid custom {_label}: {_value!r}")

        # Laravel/PHP defaults when root FS may be read-only: app reads these
        # from the process environment even without a writable .env file.
        if platform in ("laravel", "php", "lumen", "symfony"):
            # The public deployment endpoint is HTTPS while Traefik forwards
            # traffic to the container over HTTP. Laravel otherwise may build
            # absolute asset URLs with http://, causing browser Mixed Content
            # blocks for Vite CSS/JS. Keep explicit tenant settings intact and
            # provide secure platform defaults for APP_URL/ASSET_URL.
            try:
                from django.conf import settings as _django_settings
                _deployment_domain = str(getattr(_django_settings, "DEPLOYMENT_DOMAIN", "") or "").strip().strip(".")
            except Exception:
                _deployment_domain = ""
            try:
                _service_host = str(service.get_docker_service_name() or "").strip()
            except Exception:
                _service_host = ""
            if url_mode != "disabled":
                _auto_public_url = ""
                if _deployment_domain and _service_host:
                    _auto_public_url = f"https://{_service_host}.{_deployment_domain}"
                _public_url = custom_public_url if url_mode == "custom" and custom_public_url else _auto_public_url
                _asset_url = custom_asset_url if url_mode == "custom" and custom_asset_url else _public_url
                if _public_url:
                    environment.setdefault("APP_URL", _public_url)
                    environment.setdefault("PUBLIC_URL", _public_url)
                if _asset_url:
                    environment.setdefault("ASSET_URL", _asset_url)
                # Keep proxy HTTPS detection automatic unless the entire URL
                # policy is explicitly disabled.
                environment.setdefault("HTTPS", "on")
                environment.setdefault("REQUEST_SCHEME", "https")
                environment.setdefault("TRUSTED_PROXIES", "*")

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

        endpoint_specs = []
        if platform == "docker" and docker_runtime_source.get("port"):
            endpoint_specs.append(
                EndpointSpec(
                    name="docker-web",
                    target_port=int(docker_runtime_source["port"]),
                    published_port=None,
                    protocol="http",
                    exposure="public" if docker_runtime_source.get("public") else "internal",
                    hostname=str(cfg.get("public_host") or cfg.get("domain") or ""),
                    path="",
                    tls=False,
                    enabled=True,
                    process="web",
                    metadata={
                        "source": "docker-compose" if cfg.get("source_kind") == "compose" else "dockerfile",
                        "source_file": str((cfg.get("docker_source_report") or {}).get("source_file") or ""),
                    },
                )
            )
        elif runtime_graph is not None:
            for raw_endpoint in runtime_graph.endpoints:
                endpoint_hostname = str(raw_endpoint.hostname or "").strip()
                # Ready App public DNS is a platform-owned identity derived
                # from the actual Service row. Never let an old revision
                # snapshot, placeholder, or stale endpoint hostname create a
                # Traefik router for a different host.
                if (
                    str(getattr(service, "source_kind", "") or "").lower() == "catalog"
                    and raw_endpoint.exposure == "public"
                    and raw_endpoint.enabled
                ):
                    try:
                        from services.serializers import _service_host
                        canonical_host = str(_service_host(service) or "").strip()
                    except Exception:
                        canonical_host = ""
                    if canonical_host:
                        endpoint_hostname = canonical_host
                endpoint_specs.append(
                    EndpointSpec(
                        name=raw_endpoint.name,
                        target_port=raw_endpoint.target_port,
                        published_port=raw_endpoint.published_port,
                        protocol=raw_endpoint.protocol,
                        exposure=raw_endpoint.exposure,
                        hostname=endpoint_hostname,
                        path=raw_endpoint.path,
                        tls=raw_endpoint.tls,
                        enabled=raw_endpoint.enabled,
                        process=raw_endpoint.process,
                        metadata=raw_endpoint.metadata,
                    )
                )

        if platform == "docker" and docker_runtime_source:
            source_command = cfg.get("start_command")
            if source_command:
                cfg["processes"] = [{
                    "name": "web",
                    "process_type": "web",
                    "command": source_command,
                    "entrypoint": None,
                    "replicas": 1,
                    "enabled": True,
                    "environment": {},
                }]
                runtime_options["processes"] = list(cfg["processes"])

        networks: list[tuple[str, str]] = []
        if getattr(service, "network", None) is not None and getattr(service.network, "name", None):
            networks.append((service.network.get_docker_network_name(), "overlay"))

        volume_specs = self._volume_specs(deploy_item, platform=platform)
        execution_plan = self._compile_native_plan(
            deploy_item=deploy_item,
            service=service,
            container_name=container_name,
            runtime_graph=runtime_graph,
            environment=environment,
            runtime_options=runtime_options,
            resource_limits=resource_limits,
            networks=networks,
            volume_specs=volume_specs,
            endpoint_specs=endpoint_specs,
            healthcheck_path=healthcheck_path,
            healthcheck_expected_status=expected_status,
            healthcheck_timeout=healthcheck_timeout,
        )

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

        if swarm_enabled() and execution_plan is not None:
            return self._execute_native_swarm_lifecycle(
                deploy_item,
                container_name,
                state_tracker,
                cfg=cfg,
                execution_plan=execution_plan,
                dockerfile_text=dockerfile_text,
                zip_path=zip_path,
                platform=platform,
                resource_limits=resource_limits,
                build_resource_policy=build_resource_policy,
                build_options=build_options,
                runtime_options=runtime_options,
                networks=networks,
                volume_specs=volume_specs,
                endpoint_specs=endpoint_specs,
                environment=environment,
                port=port,
                server_type=server_type,
                celery=celery,
                celery_beat=celery_beat,
                entry_point=entry_point,
                worker_count=worker_count,
                runtime_version=(cfg.get("runtime_version") or cfg.get("node_version") or cfg.get("php_version")
                    or cfg.get("python_version") or cfg.get("django_python_version") or cfg.get("go_version")
                    or cfg.get("dotnet_version")),
                package_manager=package_manager,
                working_directory=(cfg.get("working_directory") or cfg.get("working_dir")
                    or runtime_options.get("working_directory") or "/app"),
                build_dir=build_dir,
                install_command=install_command,
                build_command=build_command,
                start_command=cfg.get("start_command"),
                frontend=dict(cfg.get("frontend") or {}),
                document_root=cfg.get("document_root") or cfg.get("resolved_paths", {}).get("document_root"),
                static_dir=cfg.get("static_dir") or cfg.get("resolved_paths", {}).get("static_dir"),
                media_dir=cfg.get("media_dir") or cfg.get("resolved_paths", {}).get("media_dir"),
                url_handling=url_handling,
                healthcheck_path=healthcheck_path,
                healthcheck_expected_status=expected_status,
                healthcheck_timeout=healthcheck_timeout,
            )

        deployer = DeployFacade(
            name=container_name,
            tag=_docker_tag_from_deploy(deploy_item.version),
            zip_filename=zip_path,
            dockerfile_text=dockerfile_text,
            max_cpu=resource_limits["cpu"],
            max_ram=resource_limits["memory_mb"],
            networks=networks,
            volumes=volume_specs,
            port=port,
            # The Service flag is the default compatibility value, but an
            # explicit runtime.read_only setting is a deliberate per-deployment
            # override and must not be silently ignored.
            read_only=(
                as_bool(runtime_options["read_only"])
                if "read_only" in runtime_options
                else bool(service.read_only)
            ),
            platform=platform,
            platform_type=service.plan.plan_type,
            event_sink=state_tracker.event_sink,
            deployment_id=deploy_item.id,
            deadline=DeploymentDeadline.from_deployment(deploy_item),
            environment=environment,
            server_type=server_type,
            celery=celery,
            celery_beat=celery_beat,
            entry_point=entry_point,
            worker_count=worker_count,
            resource_limits=resource_limits,
            build_resource_policy=build_resource_policy,
            build_options={
                **build_options,
                "build_command": build_command,
                "install_command": install_command,
                "build_dir": build_dir,
                "package_manager": package_manager,
                "build_args": {
                    **build_environment,
                    **dict(build_options.get("build_args") or {}),
                },
            },
            runtime_options=runtime_options,
            labels={
                **dict(cfg.get("labels") or {}),
                "deployment.id": str(deploy_item.pk),
                "service.id": str(service.pk),
                "release.id": str(getattr(deploy_item, "release_id", "") or ""),
                "revision.id": str(getattr(deploy_item, "revision_id", "") or ""),
            },
            public_host=cfg.get("public_host") or cfg.get("domain"),
            endpoints=endpoint_specs,
            activation_callback=activation_callback,
            execution_plan=execution_plan,
            runtime_version=(
                cfg.get("runtime_version")
                or cfg.get("node_version")
                or cfg.get("php_version")
                or cfg.get("python_version")
                or cfg.get("django_python_version")
                or cfg.get("go_version")
                or cfg.get("dotnet_version")
            ),
            package_manager=package_manager,
            working_directory=(
                cfg.get("working_directory")
                or cfg.get("working_dir")
                or runtime_options.get("working_directory")
                or (
                    "/var/www/html"
                    if (
                        str(cfg.get("catalog_id") or "").strip().lower() == "wordpress"
                        and str(cfg.get("catalog_service_key") or "").strip().lower() == "wordpress"
                    )
                    else "/app"
                )
            ),
            build_dir=build_dir,
            install_command=install_command,
            build_command=build_command,
            start_command=cfg.get("start_command"),
            frontend=dict(cfg.get("frontend") or {}),
            document_root=cfg.get("document_root") or cfg.get("resolved_paths", {}).get("document_root"),
            static_dir=cfg.get("static_dir") or cfg.get("resolved_paths", {}).get("static_dir"),
            media_dir=cfg.get("media_dir") or cfg.get("resolved_paths", {}).get("media_dir"),
            url_handling=url_handling,
            healthcheck_path=healthcheck_path,
            healthcheck_expected_status=expected_status,
            healthcheck_timeout=healthcheck_timeout,
            # Base runtime images are resolved by DeploymentOrchestrator after
            # project auto-detection. Do not reference a local ``config`` here;
            # no such variable exists in this service layer.
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
                fresh = Deploy.objects.filter(pk=deploy_item.pk).values("cancel_requested", "stage").first()
                if not fresh or not fresh.get("cancel_requested"):
                    return False
                if fresh.get("stage") == "timeout_requested":
                    return "timeout"
                return True
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
                stage=getattr(result, "stage", None) or "orchestrator",
                user_message=result.message or "Deployment failed during orchestration.",
                technical_message=(
                    error_details.get("technical_message")
                    or getattr(result, "error", None)
                    or result.message
                ),
                code=error_details.get("error_code") or "DEPLOYMENT_ORCHESTRATION_ERROR",
                category=error_details.get("error_category") or "deployment_error",
                recoverable=bool(error_details.get("recoverable", False)),
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
                    "error_code": error_details.get("error_code"),
                    "error_category": error_details.get("error_category"),
                    "technical_message": error_details.get("technical_message"),
                },
            )
        return result

    def _execute_native_swarm_lifecycle(
        self,
        deploy_item,
        container_name: str,
        state_tracker: DjangoDeploymentState,
        *,
        cfg: dict,
        execution_plan,
        dockerfile_text: str,
        zip_path: str,
        platform: str,
        resource_limits: dict,
        build_resource_policy: dict,
        build_options: dict,
        runtime_options: dict,
        networks: list[tuple[str, str]],
        volume_specs: list[VolumeSpec],
        endpoint_specs: list[EndpointSpec],
        environment: dict[str, str],
        port: int | None,
        server_type,
        celery: bool,
        celery_beat: bool,
        entry_point,
        worker_count: int,
        runtime_version,
        package_manager,
        working_directory: str,
        build_dir,
        install_command,
        build_command,
        start_command,
        frontend: dict,
        document_root,
        static_dir,
        media_dir,
        url_handling: dict,
        healthcheck_path,
        healthcheck_expected_status,
        healthcheck_timeout: float,
    ):
        """Execute the production Swarm path through the native lifecycle contract."""
        import hashlib
        import json
        import platform as platform_module
        from dataclasses import replace

        from deployments.runtime.contract import RuntimeIdentity
        from deploy.models import BuildArtifact, Release

        resolver = DjangoRuntimeSelectionResolver()
        selection = resolver.resolve(
            service=deploy_item.service,
            revision=getattr(deploy_item, "revision", None),
            deployment=deploy_item,
            probe=True,
        )
        if selection.backend != RuntimeBackend.SWARM.value:
            raise RuntimeUnavailableError(
                "The selected runtime backend is not Docker Swarm.",
                code="runtime_backend_mismatch",
                details={"backend": selection.backend},
            )

        tag = _docker_tag_from_deploy(deploy_item.version)
        build_networks = [
            NetworkSpec(name=str(name), driver=str(driver or "overlay"))
            for name, driver in networks
        ]
        deployment_deadline = DeploymentDeadline.from_deployment(deploy_item)
        build_config = DeploymentConfig(
            name=container_name,
            tag=tag,
            zip_path=zip_path,
            dockerfile_template=dockerfile_text,
            max_cpu=float(resource_limits.get("cpu") or 1.0),
            max_ram=int(resource_limits.get("memory_mb") or 512),
            networks=build_networks,
            volumes=list(volume_specs),
            port=port,
            read_only=bool(runtime_options.get("read_only", getattr(deploy_item.service, "read_only", True))),
            platform=platform,
            platform_type=str(getattr(getattr(deploy_item.service, "plan", None), "plan_type", "") or ""),
            runtime_version=runtime_version,
            package_manager=package_manager,
            working_directory=working_directory,
            build_dir=build_dir,
            install_command=install_command,
            build_command=build_command,
            start_command=start_command,
            frontend=dict(frontend or {}),
            static_dir=static_dir,
            media_dir=media_dir,
            environment=dict(environment),
            server_type=server_type,
            celery=celery,
            celery_beat=celery_beat,
            entry_point=entry_point,
            worker_count=int(worker_count or 1),
            resource_limits=dict(resource_limits),
            build_options=dict(build_options),
            build_resource_policy=dict(build_resource_policy),
            runtime_options=dict(runtime_options),
            labels={
                **dict(cfg.get("labels") or {}),
                "deployment.id": str(deploy_item.pk),
                "service.id": str(deploy_item.service_id),
                "revision.id": str(getattr(deploy_item, "revision_id", "") or ""),
                "managed-by": "django-paas-deployer",
            },
            public_host=cfg.get("public_host") or cfg.get("domain"),
            health_timeout=int(float(cfg.get("health_timeout") or 60)),
            health_interval=float(cfg.get("health_interval") or 1.0),
            healthcheck_path=healthcheck_path,
            healthcheck_expected_status=tuple(healthcheck_expected_status or (200, 204)),
            healthcheck_timeout=float(healthcheck_timeout or 5.0),
            document_root=document_root,
            url_handling=dict(url_handling or {}),
            endpoints=list(endpoint_specs),
        )

        def publish(event: DeploymentExecutionEvent) -> None:
            state_tracker.event_sink(
                DeploymentEvent(
                    stage=event.stage,
                    message=event.message,
                    level=event.level,
                    progress=event.progress,
                    details=dict(event.details or {}),
                )
            )

        operation_key = (
            f"deploy:{deploy_item.pk}:"
            f"revision:{getattr(deploy_item, 'revision_id', '') or 'none'}"
        )
        context = DeploymentExecutionContext(
            deployment_id=str(deploy_item.pk),
            service_id=str(deploy_item.service_id),
            revision_id=str(getattr(deploy_item, "revision_id", "") or "") or None,
            worker_task_id=str(getattr(deploy_item, "execution_task_id", "") or "") or None,
            operation_key=operation_key,
            runtime_selection=replace(
                selection,
                required_capabilities=execution_plan.required_capabilities,
            ),
            owns_execution=lambda: StateManager.heartbeat_deploy(
                deploy_item.pk,
                task_id=getattr(deploy_item, "execution_task_id", None),
                stage="native_execution",
            ),
            cancellation_requested=lambda: bool(
                Deploy.objects.filter(pk=deploy_item.pk)
                .values_list("cancel_requested", flat=True)
                .first()
            ),
            publish=publish,
        )
        store = DjangoDeploymentLifecycleStore(
            int(deploy_item.pk),
            task_id=getattr(deploy_item, "execution_task_id", None),
        )
        runtime = resolver.registry.resolve_adapter(selection)

        def build_plan(current_context):
            current_context.assert_can_continue()
            current_context.emit(
                "prepare_resources",
                "Preparing the immutable application artifact.",
                progress=15,
            )

            from deploy.base_images import ensure_base_images
            from deployments.core.converter import convert_zip_to_tar
            from deployments.core.dockerfile import DockerfileGenerator
            from deployments.core.manager.image_manager import Image
            from deploy.build_cache import get_build_cache_sources

            resolved_bases = ensure_base_images(
                build_config,
                build_policy=dict(build_resource_policy),
                logger_sink=None,
                deployment_id=deploy_item.pk,
            )
            build_config.base_images = dict(resolved_bases or {})

            tar_stream = convert_zip_to_tar(zip_path)
            rendered_dockerfile = DockerfileGenerator().render(
                platform=platform,
                dockerfile_template=dockerfile_text,
                tar_stream=tar_stream,
                config=build_config,
                logger=None,
            )
            current_context.assert_can_continue()
            current_context.emit(
                "image_build",
                "Building the immutable application artifact.",
                progress=25,
            )

            cache_sources = get_build_cache_sources(str(deploy_item.pk))
            image = Image(
                container_name,
                tag,
                rendered_dockerfile,
                tar_stream,
                max_cpu=build_config.max_cpu,
                max_ram=build_config.max_ram,
                build_options=dict(build_options),
                build_resource_policy=dict(build_resource_policy),
                deployment_id=deploy_item.pk,
                cache_sources=cache_sources,
                build_labels={
                    "io.passdeployer.deployment": str(deploy_item.pk),
                    "io.passdeployer.service": str(deploy_item.service_id),
                    "io.passdeployer.revision": str(deploy_item.revision_id or ""),
                },
            )
            built_image = image.create(
                cancel_check=current_context.cancellation_requested,
                timeout_seconds=deployment_deadline.bound(3600.0) or 0.0,
            )
            current_context.assert_can_continue()

            attrs = getattr(built_image, "attrs", {}) or {}
            repo_digests = list(attrs.get("RepoDigests") or ())
            artifact_digest = str(
                str(repo_digests[0]).split("@", 1)[-1]
                if repo_digests and "@" in str(repo_digests[0])
                else getattr(built_image, "id", "") or ""
            )
            if not artifact_digest:
                raise DeploymentValidationError(
                    "The Docker builder returned no immutable artifact digest.",
                    stage="image_build",
                    code="ARTIFACT_DIGEST_MISSING",
                    user_message="The application artifact could not be given an immutable identity.",
                )

            source_hasher = hashlib.sha256()
            with open(zip_path, "rb") as source_file:
                for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                    source_hasher.update(chunk)
            source_digest = source_hasher.hexdigest()
            build_definition_digest = hashlib.sha256(
                json.dumps(
                    {
                        "platform": platform,
                        "dockerfile": rendered_dockerfile,
                        "build_options": dict(build_options),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("utf-8")
            ).hexdigest()
            base_image_digests = sorted({
                str(value).split("@", 1)[-1]
                for value in dict(build_config.base_images or {}).values()
                if "@sha256:" in str(value)
            })

            from deployments.runtime.artifacts import ArtifactReference

            current_context.assert_can_continue()
            published = runtime.artifact_registry.ensure_available(
                ArtifactReference(
                    digest=artifact_digest,
                    image_ref=str(container_name + ":" + tag),
                    source_digest=source_digest,
                ),
                service_name=container_name,
                tag=tag,
                operation_key=current_context.operation_key,
            )
            published_image_ref = str(published.image_ref)

            artifact, _ = BuildArtifact.objects.get_or_create(
                digest=artifact_digest,
                defaults={
                    "image_ref": published_image_ref,
                    "source_digest": source_digest,
                    "build_definition_digest": build_definition_digest,
                    "base_image_digests": base_image_digests,
                    "build_context_identity": source_digest,
                    "builder_backend": "docker-engine-buildkit",
                    "platform_architecture": str(platform_module.machine() or ""),
                    "provenance": {
                        "deployment_id": str(deploy_item.pk),
                        "service_id": str(deploy_item.service_id),
                        "revision_id": str(deploy_item.revision_id or ""),
                    },
                    "created_by_id": getattr(deploy_item, "created_by_id", None),
                },
            )

            runtime_plan = replace(
                execution_plan,
                runtime_selection=replace(
                    execution_plan.runtime_selection,
                    availability=selection.availability,
                ),
                image_ref=str(artifact.image_ref),
                artifact_digest=str(artifact.digest),
                release_id=None,
                labels={
                    **dict(getattr(execution_plan, "labels", {}) or {}),
                    "deployment.id": str(deploy_item.pk),
                    "service.id": str(deploy_item.service_id),
                    "revision.id": str(deploy_item.revision_id or ""),
                    "artifact.digest": str(artifact.digest),
                    "managed-by": "django-paas-deployer",
                },
            )
            configured_release_spec = dict(getattr(runtime_plan, "release_spec", {}) or {})
            if not configured_release_spec and platform == "laravel" and bool(cfg.get("migrate", True)):
                primary_replicas = 1
                primary_process = next(
                    (
                        item for item in getattr(runtime_plan.process_graph, "processes", ())
                        if str(getattr(item, "name", "")).lower() == "web"
                    ),
                    None,
                )
                if primary_process is not None:
                    primary_replicas = int(getattr(primary_process, "replicas", 1) or 1)
                configured_release_spec = ReleaseSpec(
                    command=("php", "artisan", "migrate", "--force"),
                    timeout=float(cfg.get("release_command_timeout") or 300.0),
                    failure_policy="block",
                    run_once=(primary_replicas == 1),
                    idempotency_key=f"release:{deploy_item.revision_id}:laravel-migrate",
                    execution_backend="runtime-entrypoint",
                ).as_dict()
                runtime_plan = replace(
                    runtime_plan,
                    release_spec=configured_release_spec,
                )
            if configured_release_spec.get("command"):
                runtime_plan = replace(
                    runtime_plan,
                    release_spec=configured_release_spec,
                )

            runtime_spec = RuntimeSpec.from_plan(
                runtime_plan,
                image_digest=str(artifact.digest),
            )
            previous_release = (
                Release.objects.filter(
                    service_id=deploy_item.service_id,
                    status="promoted",
                )
                .order_by("-promoted_at", "-created_at")
                .first()
            )
            release_spec = dict(getattr(runtime_plan, "release_spec", {}) or {})
            fingerprint = Release.fingerprint(
                service_id=deploy_item.service_id,
                revision_id=deploy_item.revision_id,
                artifact_digest=artifact.digest,
                runtime_spec=runtime_spec.as_dict(),
                rollout_policy=dict(getattr(runtime_plan, "rollout_policy", {}) or {}),
                health_policy=dict(getattr(runtime_plan, "health_policy", {}) or {}),
                release_command=release_spec,
            )
            release, _ = Release.objects.get_or_create(
                identity_fingerprint=fingerprint,
                defaults={
                    "service_id": deploy_item.service_id,
                    "revision_id": deploy_item.revision_id,
                    "artifact_id": artifact.pk,
                    "runtime_spec": runtime_spec.as_dict(),
                    "rollout_policy": dict(getattr(runtime_plan, "rollout_policy", {}) or {}),
                    "health_policy": dict(getattr(runtime_plan, "health_policy", {}) or {}),
                    "release_command": release_spec,
                    "previous_release_id": getattr(previous_release, "pk", None),
                    "provenance": {
                        "source_digest": source_digest,
                        "build_definition_digest": build_definition_digest,
                        "artifact_digest": artifact.digest,
                    },
                    "created_by_id": getattr(deploy_item, "created_by_id", None),
                },
            )
            runtime_plan = replace(runtime_plan, release_id=str(release.pk))
            if release.status != "ready":
                Release.objects.filter(pk=release.pk).update(
                    status="ready",
                    updated_at=__import__("django.utils.timezone", fromlist=["now"]).now(),
                )

            if previous_release is not None and getattr(previous_release, "artifact_id", None):
                previous_graph = ServiceRuntimeGraph.from_revision(previous_release.revision)
                previous_identity = replace(
                    runtime_plan.identity,
                    revision_id=str(previous_release.revision_id),
                )
                previous_runtime = dict(previous_release.runtime_spec or {})
                previous_options = dict(
                    previous_runtime.get("runtime_options")
                    or runtime_plan.runtime_options
                    or {}
                )
                rollback_plan = replace(
                    runtime_plan,
                    identity=previous_identity,
                    process_graph=previous_graph,
                    image_ref=str(previous_release.artifact.image_ref),
                    artifact_digest=str(previous_release.artifact.digest),
                    release_id=str(previous_release.pk),
                    environment=dict(previous_graph.runtime_environment),
                    runtime_options=previous_options,
                    release_spec=dict(previous_release.release_command or {}),
                    health_policy=dict(previous_release.health_policy or {}),
                    rollout_policy=dict(previous_release.rollout_policy or {}),
                    labels={
                        **dict(getattr(runtime_plan, "labels", {}) or {}),
                        "release.id": str(previous_release.pk),
                        "revision.id": str(previous_release.revision_id),
                        "artifact.digest": str(previous_release.artifact.digest),
                        "deployment.id": str(deploy_item.pk),
                        "service.id": str(deploy_item.service_id),
                        "managed-by": "django-paas-deployer",
                    },
                    rollback_plan=None,
                )
            else:
                rollback_plan = None

            runtime_plan = replace(
                runtime_plan,
                rollback_plan=rollback_plan,
            )
            runtime_spec = RuntimeSpec.from_plan(
                runtime_plan,
                image_digest=str(artifact.digest),
            )
            Deploy.objects.filter(pk=deploy_item.pk).update(
                release_reference=release,
                artifact=artifact,
                image_ref=artifact.image_ref,
                image_digest=artifact.digest,
                runtime_revision_id=str(deploy_item.revision_id or ""),
                runtime_spec=runtime_spec.as_dict(),
                runtime_spec_sha256=runtime_spec.sha256,
                source_revision=source_digest,
            )
            current_context.emit(
                "artifact",
                "Immutable artifact and Release prepared.",
                progress=40,
                details={
                    "artifact_digest": str(artifact.digest),
                    "release_id": str(release.pk),
                },
            )
            return runtime_plan

        strategy = CallbackDeploymentStrategy(build_plan=build_plan)
        result = DeploymentLifecycleExecutor(store).execute(
            context,
            strategy,
            runtime,
            readiness_timeout=(
                deployment_deadline.bound(
                    float(cfg.get("health_timeout") or healthcheck_timeout or 60.0)
                )
                or 0.0
            ),
        )
        if result.success:
            return result
        if result.status == "cancelled":
            return result
        error = result.error
        raise OrchestratorDeploymentError(
            str(getattr(error, "user_message", None) or "Native deployment failed."),
            stage=str(getattr(error, "stage", None) or "deployment_execution"),
            user_message=str(getattr(error, "user_message", None) or "Deployment failed."),
            technical_message=str(
                getattr(error, "technical_message", None)
                or getattr(error, "message", None)
                or error
                or ""
            ),
            code=str(getattr(error, "code", None) or "DEPLOYMENT_NATIVE_FAILED"),
            category=str(getattr(error, "category", None) or "deployment_error"),
            recoverable=bool(getattr(error, "recoverable", False)),
            details=dict(result.details or {}),
        )

    @staticmethod
    def _compile_native_plan(
        *,
        deploy_item: Deploy,
        service,
        container_name: str,
        runtime_graph: ServiceRuntimeGraph | None,
        environment: dict[str, str],
        runtime_options: dict,
        resource_limits: dict,
        networks: list[tuple[str, str]],
        volume_specs: list[VolumeSpec],
        endpoint_specs: list[EndpointSpec],
        healthcheck_path,
        healthcheck_expected_status,
        healthcheck_timeout,
    ):
        """Compile the native DeploymentPlan from the normalized ServiceRevision graph."""

        if runtime_graph is None:
            return None

        network_specs = [
            NetworkSpec(name=str(name), driver=str(driver or "overlay"))
            for name, driver in networks
        ]
        resolver = ConfigurationResolver()
        resolved = resolver.resolve(
            platform_policy={"resource_limits": dict(resource_limits)},
            revision_snapshot={
                "environment": dict(environment),
                "runtime_options": dict(runtime_options),
                "networks": network_specs,
                "volumes": list(volume_specs),
                "endpoints": list(endpoint_specs),
                "health_policy": {
                    "path": healthcheck_path,
                    "expected_status": list(healthcheck_expected_status or (200, 204)),
                    "timeout": healthcheck_timeout,
                },
            },
        )
        selection = DjangoRuntimeSelectionResolver().resolve(
            service=service,
            revision=getattr(deploy_item, "revision", None),
            deployment=deploy_item,
            probe=False,
        )
        if selection.backend != RuntimeBackend.SWARM.value:
            return None
        if not selection.availability.operator_enabled:
            raise RuntimeUnavailableError(
                "The selected runtime is disabled by operator policy.",
                code="runtime_disabled",
                details={"cluster": selection.cluster},
            )
        identity = RuntimeIdentity(
            service_id=str(service.pk),
            deployment_id=str(deploy_item.pk),
            revision_id=str(getattr(deploy_item, "revision_id", "") or "") or None,
            runtime_name=str(container_name),
        )
        return DeploymentPlanCompiler().compile(
            identity=identity,
            graph=runtime_graph,
            selection=selection,
            resolved=resolved,
            image_ref=canonical_image_ref(container_name, deploy_item.version),
        )

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
                    raise DeploymentValidationError(
                        f"Persistent volume '{name}' cannot be allocated within the service storage quota.",
                        stage="volume_creation",
                        details={
                            "service_id": str(service.pk),
                            "volume": name,
                            "requested_mb": size_mb,
                            "quota_error": msg,
                            "persistence_required": True,
                        },
                    )
            except DeploymentValidationError:
                raise
            except Exception as exc:
                raise DeploymentValidationError(
                    "Persistent volume quota could not be verified.",
                    stage="volume_creation",
                    details={
                        "service_id": str(service.pk),
                        "requested_mb": size_mb,
                        "exception_type": type(exc).__name__,
                        "technical_message": str(exc),
                    },
                ) from exc
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
                raise DeploymentValidationError(
                    f"Persistent volume '{name}' could not be registered.",
                    stage="volume_creation",
                    details={
                        "service_id": str(service.pk),
                        "volume": name,
                        "requested_mb": size_mb,
                        "exception_type": type(exc).__name__,
                        "technical_message": str(exc),
                        "persistence_required": True,
                    },
                ) from exc


    @classmethod
    def _ensure_docker_source_volumes(cls, service, volume_defs: list[dict]) -> None:
        """Materialize Compose named volumes as registry-owned PassDeployer volumes."""
        if not volume_defs:
            return
        for item in volume_defs[:8]:
            target = str(item.get("target") or "").strip()
            compose_name = str(item.get("compose_name") or "").strip()
            mode = str(item.get("mode") or "rw").lower()
            if not target:
                continue
            existing = service.volumes.filter(default_bind=target).order_by("created_at").first()
            if existing is not None:
                continue
            safe_name = re.sub(r"[^a-z0-9_.-]+", "-", compose_name.lower()).strip("-") or "data"
            volume_name = f"dv-{service.id.hex[:8]}-{safe_name}"[:32]
            size_mb = 256
            ok, msg = service.can_allocate_storage(size_mb)
            if not ok:
                raise DeploymentValidationError(
                    f"Compose persistent volume '{compose_name or target}' cannot be allocated within the service storage quota.",
                    stage="volume_creation",
                    details={
                        "service_id": str(service.pk),
                        "compose_volume": compose_name,
                        "target": target,
                        "requested_mb": size_mb,
                        "quota_error": msg,
                    },
                )
            Volume.objects.create(
                name=volume_name,
                user_id=service.user_id,
                service=service,
                service_attachments={
                    str(service.id): {
                        "bind": target,
                        "mode": "ro" if mode in {"ro", "readonly"} else "rw",
                    }
                },
                default_bind=target,
                default_mode="r" if mode in {"ro", "readonly"} else "rw",
                size_mb=size_mb,
            )
            logger.info(
                "Registered Docker Compose named volume %s -> %s for service %s.",
                volume_name, target, service.pk,
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
            if plat == "docker":
                cls_source_volumes = cfg.get("docker_source_volumes") or []
                if isinstance(cls_source_volumes, list):
                    DeployService._ensure_docker_source_volumes(
                        service, cls_source_volumes
                    )
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
        except DeploymentValidationError:
            raise
        except Exception as exc:
            raise DeploymentValidationError(
                "Persistent application storage could not be prepared.",
                stage="volume_creation",
                details={
                    "service_id": str(service.id),
                    "exception_type": type(exc).__name__,
                    "technical_message": str(exc),
                },
            ) from exc

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
