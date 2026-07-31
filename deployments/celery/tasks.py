"""
deployments/celery/tasks.py
---------------------------
Celery entry-points for the deployment subsystem.

Tasks
-----
deploy          App / zip pipeline (DeployService).  Redirects DB platforms
                to run_db_deploy so a mis-routed message never builds a zip.
stop            Container stop pipeline (StopService).
run_db_deploy   Database-platform pipeline (DBDeployer).  No zip, no
                Dockerfile — credentials from Deploy.config + Service metadata.
monitor_services  Periodic reconciler (re-exported from .schedules).
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from core.global_settings.config import SERVICE_STATUS_CHOICES
from deploy.models import Deploy, DeployLog, DeploymentStatusChoices
from deployments.core.db_deployer import (
    DB_PLATFORMS,
    DBDeployer,
    validate_db_config,
)
from deployments.core.exceptions import DeploymentError
from services.models import Service

from .services.deploy_service import DeployService
from .services.stop_service import StopService
from .exceptions import (
    ContainerTimeoutError,
    DeploymentValidationError,
    InvalidServiceStateError,
    OrchestratorDeploymentError,
)
from .schedules import monitor_services  # noqa: F401  — re-export for beat

logger = logging.getLogger(__name__)


# ===========================================================================
# App deploy / stop (existing)
# ===========================================================================

@shared_task(bind=True, max_retries=3, default_retry_delay=15)
def deploy(self, deploy_id) -> None:
    logger.info("Initializing background processing for deploy_id: %s", deploy_id)

    # Guard: never run the app/zip pipeline for DB platforms
    try:
        deploy_item = (
            Deploy.objects
            .select_related("service", "service__plan")
            .filter(pk=deploy_id)
            .first()
        )
        if deploy_item is not None:
            cfg = deploy_item.config if isinstance(deploy_item.config, dict) else {}
            platform = (
                (cfg.get("platform") or "")
                or getattr(getattr(deploy_item.service, "plan", None), "platform", "")
                or ""
            )
            platform = str(platform).lower().strip()
            if platform in DB_PLATFORMS:
                logger.warning(
                    "deploy task received DB platform '%s' for deploy_id=%s; "
                    "redirecting to run_db_deploy",
                    platform,
                    deploy_id,
                )
                run_db_deploy.delay(str(deploy_id))
                return
    except Exception:
        logger.exception(
            "DB platform guard failed for deploy_id=%s; continuing app path",
            deploy_id,
        )

    try:
        DeployService().execute(deploy_id)
    except (
        InvalidServiceStateError,
        DeploymentValidationError,
        OrchestratorDeploymentError,
        ContainerTimeoutError,
    ):
        logger.exception("Deployment did not complete for deploy_id: %s", deploy_id)
    except Exception as exc:
        logger.warning("Deploy execution error; re-enqueueing (ID: %s)", deploy_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def stop(self, service_id) -> None:
    logger.info("Initializing stop for service_id: %s", service_id)
    try:
        StopService().execute(service_id)
    except InvalidServiceStateError:
        pass
    except Exception as exc:
        logger.warning("Stop error; re-enqueueing (ID: %s)", service_id)
        raise self.retry(exc=exc)


# ===========================================================================
# DB deploy
# ===========================================================================

def _resolve_platform(deploy: Deploy) -> str:
    """config.platform → service.plan.platform → empty string."""
    cfg = deploy.config if isinstance(getattr(deploy, "config", None), dict) else {}
    p = str(cfg.get("platform") or "").strip().lower()
    if p:
        return p
    plan = getattr(getattr(deploy, "service", None), "plan", None)
    if plan is not None and getattr(plan, "platform", None):
        return str(plan.platform).strip().lower()
    return ""


def _build_db_cfg(deploy: Deploy, service: Service) -> dict[str, Any]:
    """
    Merge Deploy.config credentials with live Service metadata
    (plan limits, volumes, network) so DBDeployer has everything it needs.
    """
    cfg: dict[str, Any] = {}
    raw = deploy.config if isinstance(deploy.config, dict) else {}
    cfg.update(raw)

    platform = _resolve_platform(deploy)
    if platform:
        cfg["platform"] = platform

    plan = getattr(service, "plan", None)
    if plan is not None:
        if cfg.get("max_cpu") is None and getattr(plan, "max_cpu", None) is not None:
            cfg["max_cpu"] = plan.max_cpu
        if cfg.get("max_ram") is None and getattr(plan, "max_ram", None) is not None:
            cfg["max_ram"] = plan.max_ram

    if not cfg.get("networks"):
        networks: list[str] = []
        net = getattr(service, "network", None)
        if net is not None and getattr(net, "name", None):
            networks.append(net.name)
        networks.append("proxy_net")
        cfg["networks"] = networks

    if not cfg.get("volumes"):
        volumes: list[dict] = []
        try:
            for vol in service.volumes.all():
                bind = getattr(vol, "bind", None) or getattr(vol, "default_bind", None)
                mode = (
                    getattr(vol, "mode", None)
                    or getattr(vol, "default_mode", None)
                    or "rw"
                )
                attachments = getattr(vol, "service_attachments", None) or {}
                if isinstance(attachments, dict):
                    att = attachments.get(str(service.pk)) or {}
                    bind = att.get("bind") or bind
                    mode = att.get("mode") or mode
                if bind:
                    volumes.append(
                        {
                            "source": vol.name,
                            "target": bind,
                            "mode": mode or "rw",
                        }
                    )
        except Exception:
            logger.exception(
                "Failed to collect volumes for service %s; continuing without",
                service.pk,
            )
        if volumes:
            cfg["volumes"] = volumes

    return cfg


def _create_deploy_log(
    deploy: Deploy,
    stage: str,
    message: str,
    *,
    level: str = "info",
    event_type: str = "deployment.db",
    progress: int | None = None,
    details: dict | None = None,
    exception_type: str = "",
    traceback_str: str = "",
) -> None:
    try:
        DeployLog.objects.create(
            deploy=deploy,
            service=deploy.service,
            stage=stage,
            event_type=event_type,
            level=level,
            message=message,
            progress=progress,
            details=details or {},
            exception_type=exception_type,
            traceback=traceback_str,
        )
    except Exception:
        logger.exception(
            "Failed to write DeployLog for deploy %s stage=%s", deploy.pk, stage
        )


def _mark_success(deploy: Deploy, service: Service, result_message: str) -> None:
    now = timezone.now()
    with transaction.atomic():
        Deploy.objects.filter(pk=deploy.pk).update(
            status=DeploymentStatusChoices.SUCCEEDED,
            stage="finished",
            progress=100,
            status_message=result_message or "Database deployed successfully.",
            error_message="",
            completed_at=now,
        )
        Service.objects.filter(pk=service.pk).update(
            status=SERVICE_STATUS_CHOICES.RUNNING,
            deployed_at=now,
            deploy_started=None,
            task_id=None,
        )
    _create_deploy_log(
        deploy,
        stage="finished",
        message=result_message or "Database deployed successfully.",
        level="info",
        progress=100,
    )
    logger.info("DB deploy succeeded: deploy=%s service=%s", deploy.pk, service.pk)


def _mark_failure(
    deploy: Deploy,
    service: Service,
    message: str,
    *,
    stage: str = "deployment_failed",
    details: dict | None = None,
    tb: str = "",
) -> None:
    now = timezone.now()
    with transaction.atomic():
        Deploy.objects.filter(pk=deploy.pk).update(
            status=DeploymentStatusChoices.FAILED,
            stage=stage,
            error_message=message,
            status_message="Database deployment failed.",
            completed_at=now,
        )
        Service.objects.filter(pk=service.pk).exclude(
            status=SERVICE_STATUS_CHOICES.STOPPED
        ).update(
            status=SERVICE_STATUS_CHOICES.FAILED,
            deploy_started=None,
            task_id=None,
        )
    _create_deploy_log(
        deploy,
        stage=stage,
        message=message,
        level="error",
        details=details or {},
        exception_type="DBDeployError",
        traceback_str=tb,
    )
    logger.warning(
        "DB deploy failed: deploy=%s service=%s stage=%s msg=%s",
        deploy.pk,
        service.pk,
        stage,
        message,
    )


def _lock_for_db_deploy(deploy_id: str | int) -> tuple[Deploy, Service] | None:
    """
    Transition Service QUEUED → DEPLOYING and Deploy → RUNNING under row locks.

    Accepts QUEUED (normal) and DEPLOYING (retry / re-delivery) so the task
    is idempotent.
    """
    with transaction.atomic():
        try:
            deploy = (
                Deploy.objects.select_related(
                    "service",
                    "service__plan",
                    "service__network",
                )
                .select_for_update(of=("self", "service"))
                .get(pk=deploy_id)
            )
        except Deploy.DoesNotExist:
            logger.error("run_db_deploy: Deploy %s does not exist", deploy_id)
            return None

        service = deploy.service
        if service is None:
            logger.error("run_db_deploy: Deploy %s has no service", deploy_id)
            return None

        allowed = (
            SERVICE_STATUS_CHOICES.QUEUED,
            SERVICE_STATUS_CHOICES.DEPLOYING,
        )
        if service.status not in allowed:
            logger.info(
                "run_db_deploy: skipping deploy=%s — service status is %s "
                "(expected QUEUED/DEPLOYING)",
                deploy_id,
                service.status,
            )
            return None

        now = timezone.now()
        service.status = SERVICE_STATUS_CHOICES.DEPLOYING
        service.deploy_started = service.deploy_started or now
        service.save(update_fields=["status", "deploy_started"])

        deploy.status = DeploymentStatusChoices.RUNNING
        deploy.started_at = deploy.started_at or now
        deploy.stage = "starting"
        deploy.progress = max(deploy.progress or 0, 5)
        deploy.status_message = "Database deployment in progress."
        deploy.save(
            update_fields=[
                "status",
                "started_at",
                "stage",
                "progress",
                "status_message",
            ]
        )
        return deploy, service


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, DeploymentError) and not getattr(exc, "recoverable", False):
        return False
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    markers = (
        "timeout",
        "connection",
        "temporarily",
        "unavailable",
        "network",
        "docker",
        "apierror",
        "servererror",
    )
    return any(m in name or m in text for m in markers)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=20,
    name="deployments.celery.tasks.run_db_deploy",
)
def run_db_deploy(self, deploy_id: str | int) -> None:
    """
    Execute a database-platform deployment via DBDeployer.

    Enqueued by:
      - services.apis.start_service_apiview  (when platform ∈ DB_PLATFORMS)
      - deployments.celery.tasks.deploy      (guard redirect)
    """
    logger.info("run_db_deploy started for deploy_id=%s", deploy_id)

    locked = _lock_for_db_deploy(deploy_id)
    if locked is None:
        return

    deploy, service = locked
    container_name = service.get_docker_service_name()
    platform = _resolve_platform(deploy)

    if platform not in DB_PLATFORMS:
        msg = (
            f"Platform '{platform}' is not a supported DB platform. "
            f"Supported: {sorted(DB_PLATFORMS)}"
        )
        _mark_failure(deploy, service, msg, stage="validation")
        return

    if getattr(deploy, "cancel_requested", False):
        _mark_failure(
            deploy,
            service,
            "Deployment cancelled before execution.",
            stage="cancelled",
        )
        Service.objects.filter(pk=service.pk).update(
            status=SERVICE_STATUS_CHOICES.STOPPED,
            task_id=None,
            deploy_started=None,
        )
        return

    cfg = _build_db_cfg(deploy, service)

    errors = validate_db_config(platform, cfg)
    if errors:
        msg = "DB config validation failed: " + "; ".join(errors)
        _mark_failure(
            deploy,
            service,
            msg,
            stage="validation",
            details={"errors": errors},
        )
        return

    _create_deploy_log(
        deploy,
        stage="validation",
        message=f"Config validated for platform '{platform}'.",
        progress=10,
        details={"platform": platform, "container": container_name},
    )

    event_sink = None
    try:
        from deploy.sink import DBAndChannelEventSink

        event_sink = DBAndChannelEventSink(deploy.pk)
    except Exception:
        logger.debug("Event sink unavailable for deploy %s", deploy.pk)

    try:
        result = DBDeployer().deploy(
            container_name=container_name,
            platform=platform,
            cfg=cfg,
            event_sink=event_sink,
            deployment_id=str(deploy.pk),
        )
    except Exception as exc:
        tb = traceback.format_exc()
        logger.exception(
            "DBDeployer raised for deploy=%s container=%s",
            deploy.pk,
            container_name,
        )
        if self.request.retries < self.max_retries and _is_retryable(exc):
            logger.warning(
                "Retrying run_db_deploy (attempt %s) for deploy=%s: %s",
                self.request.retries + 1,
                deploy.pk,
                exc,
            )
            raise self.retry(exc=exc)

        _mark_failure(
            deploy,
            service,
            str(exc) or "Unexpected error during database deployment.",
            stage=getattr(exc, "stage", "deployment_failed"),
            details={"error": str(exc)},
            tb=tb,
        )
        return

    if result.success:
        _mark_success(deploy, service, result.message)
    else:
        _mark_failure(
            deploy,
            service,
            result.message or result.error or "Database deployment failed.",
            stage="deployment_failed",
            details=result.details or {},
        )
