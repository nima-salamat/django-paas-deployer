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

Key changes vs. legacy:
  * Uses the unified ``deployments.common.parse_config`` (was a triplicate copy).
  * Uses the unified exception hierarchy from
    ``deployments.common.exceptions`` (was two parallel hierarchies that
    silently missed each other in ``except`` clauses).
  * ``deploy`` retry now respects the ``recoverable`` flag on
    ``DeploymentError`` subclasses — known-permanent errors are not retried.
  * ``run_db_deploy`` is now strictly idempotent: ``_lock_for_db_deploy``
    no longer accepts DEPLOYING (which previously caused duplicate
    task delivery to forcefully remove + recreate the container).
    Duplicate delivery now no-ops cleanly.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from core.global_settings.config import SERVICE_STATUS_CHOICES  # type: ignore
from deploy.models import Deploy, DeployLog, DeploymentStatusChoices  # type: ignore
from deployments.core.db_deployer import (
    DB_PLATFORMS,
    DBDeployer,
    validate_db_config,
)
from deployments.common import parse_config, as_bool
from deployments.common.exceptions import (
    DeploymentError,
    InvalidServiceStateError,
    DeploymentValidationError,
    ContainerTimeoutError,
    OrchestratorDeploymentError,
)
from deployments.common.retry import is_retryable_exception
from deployments.core.state.locks import acquire_service_deployment_lock
from services.models import Service  # type: ignore

from .services.deploy_service import DeployService
from .services.stop_service import StopService
from .schedules import monitor_services  # noqa: F401  — re-export for beat

logger = logging.getLogger(__name__)


# ===========================================================================
# App deploy / stop
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
            cfg = parse_config(deploy_item.config) if isinstance(deploy_item.config, dict) else {}
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
                    platform, deploy_id,
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
    except (InvalidServiceStateError, DeploymentValidationError,
            OrchestratorDeploymentError, ContainerTimeoutError):
        # Permanent errors — log but do NOT retry.
        logger.exception("Deployment did not complete for deploy_id: %s", deploy_id)
    except DeploymentError as exc:
        # DeploymentError with recoverable=True MAY be retried.  Others
        # are permanent.  Legacy code retried on ANY DeploymentError,
        # wasting resources on bad Dockerfiles.
        if getattr(exc, "recoverable", False) and self.request.retries < self.max_retries:
            logger.warning(
                "Recoverable deployment error for deploy_id=%s (attempt %d/%d): %s",
                deploy_id, self.request.retries + 1, self.max_retries + 1, exc,
            )
            raise self.retry(exc=exc)
        logger.exception("Permanent deployment error for deploy_id: %s", deploy_id)
    except Exception as exc:
        # Unknown errors are treated as transient — retry up to max.
        if self.request.retries < self.max_retries:
            logger.warning(
                "Deploy execution error; re-enqueueing (ID: %s, attempt %d/%d)",
                deploy_id, self.request.retries + 1, self.max_retries + 1,
            )
            raise self.retry(exc=exc)
        logger.exception("Deploy exhausted retries for deploy_id: %s", deploy_id)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def stop(self, service_id) -> None:
    logger.info("Initializing stop for service_id: %s", service_id)
    try:
        StopService().execute(service_id)
    except InvalidServiceStateError:
        pass
    except Exception as exc:
        if self.request.retries < self.max_retries:
            logger.warning(
                "Stop error; re-enqueueing (ID: %s, attempt %d/%d)",
                service_id, self.request.retries + 1, self.max_retries + 1,
            )
            raise self.retry(exc=exc)
        logger.exception("Stop exhausted retries for service_id: %s", service_id)


# ===========================================================================
# DB deploy helpers
# ===========================================================================

def _resolve_platform(deploy: Deploy) -> str:
    """config.platform -> service.plan.platform -> empty string."""
    cfg = parse_config(getattr(deploy, "config", None))
    p = str(cfg.get("platform") or "").strip().lower()
    if p:
        return p
    plan = getattr(getattr(deploy, "service", None), "plan", None)
    if plan is not None and getattr(plan, "platform", None):
        return str(plan.platform).strip().lower()
    return ""


def _collect_service_volumes(service: Service) -> list[dict]:
    """
    Resolve volumes attached to a service without assuming a reverse
    relation named ``volumes`` exists on the Service model.
    """
    volumes: list[dict] = []
    seen: set[str] = set()

    def _add(vol) -> None:
        name = getattr(vol, "name", None)
        if not name or name in seen:
            return
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
        if not bind:
            return
        seen.add(name)
        volumes.append({"source": name, "target": bind, "mode": mode or "rw"})

    rel = getattr(service, "volumes", None)
    if rel is not None and hasattr(rel, "all"):
        try:
            for vol in rel.all():
                _add(vol)
        except Exception:
            logger.exception(
                "service.volumes.all() failed for service %s", service.pk
            )

    if not volumes:
        try:
            from django.db.models import Q
            from services.models import Volume  # type: ignore

            qs = Volume.objects.filter(
                Q(service_id=service.pk)
                | Q(service_attachments__has_key=str(service.pk))
            )
            for vol in qs:
                _add(vol)
        except Exception:
            logger.debug(
                "Volume model query unavailable for service %s; skipping",
                service.pk, exc_info=True,
            )

    return volumes


def _build_db_cfg(deploy: Deploy, service: Service) -> dict[str, Any]:
    """Merge Deploy.config credentials with live Service metadata."""
    cfg: dict[str, Any] = {}
    cfg.update(parse_config(getattr(deploy, "config", None)))

    platform = _resolve_platform(deploy)
    if platform:
        cfg["platform"] = platform

    if platform in ("mysql", "mariadb"):
        if not str(cfg.get("root_password") or "").strip() and str(cfg.get("password") or "").strip():
            cfg["root_password"] = str(cfg["password"])

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
        vols = _collect_service_volumes(service)
        if vols:
            cfg["volumes"] = vols

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
    """
    Write a DeployLog row on the dedicated log database.

    Uses raw IDs (not FK objects) because DeployLog lives on a separate
    database alias and Django's router would refuse FK objects.
    """
    try:
        from django.conf import settings  # type: ignore

        alias = getattr(settings, "DEPLOYMENT_LOG_DB_ALIAS", None) or "default"
        kwargs = {
            "deploy_id": deploy.pk,
            "service_id": (
                getattr(deploy, "service_id", None)
                or (deploy.service.pk if getattr(deploy, "service", None) is not None else None)
            ),
            "stage": stage,
            "event_type": event_type,
            "level": level,
            "message": message,
            "progress": progress,
            "details": details or {},
            "exception_type": exception_type,
            "traceback": traceback_str,
        }
        DeployLog.objects.using(alias).create(**kwargs)
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
        # Never overwrite a cleanly-stopped service.
        Service.objects.filter(pk=service.pk).exclude(
            status=SERVICE_STATUS_CHOICES.STOPPED
        ).update(
            status=SERVICE_STATUS_CHOICES.RUNNING,
            deployed_at=now,
            deploy_started=None,
            task_id=None,
        )
    _create_deploy_log(
        deploy, stage="finished",
        message=result_message or "Database deployed successfully.",
        level="info", progress=100,
    )
    logger.info("DB deploy succeeded: deploy=%s service=%s", deploy.pk, service.pk)


def _mark_failure(
    deploy: Deploy, service: Service, message: str, *,
    stage: str = "deployment_failed",
    details: dict | None = None, tb: str = "",
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
        deploy, stage=stage, message=message, level="error",
        details=details or {}, exception_type="DBDeployError", traceback_str=tb,
    )
    logger.warning(
        "DB deploy failed: deploy=%s service=%s stage=%s msg=%s",
        deploy.pk, service.pk, stage, message,
    )


def _lock_for_db_deploy(deploy_id: str | int) -> tuple[Deploy, Service] | None:
    """
    Transition Service QUEUED -> DEPLOYING and Deploy -> RUNNING under
    row locks.

    IDEMPOTENCY FIX: previously accepted DEPLOYING (re-entry), which
    meant duplicate Celery delivery would forcefully remove + recreate
    the container, causing downtime and potential data corruption.
    Now strictly requires QUEUED — duplicates no-op cleanly.
    """
    with transaction.atomic():
        try:
            deploy = (
                Deploy.objects.select_related(
                    "service", "service__plan", "service__network",
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

        # STRICT: only QUEUED is accepted.  A duplicate task delivery
        # (which is possible under Celery's at-least-once semantics)
        # will see DEPLOYING and no-op, leaving the original to finish.
        if service.status != SERVICE_STATUS_CHOICES.QUEUED:
            logger.info(
                "run_db_deploy: skipping deploy=%s — service status is %s "
                "(expected QUEUED). Duplicate delivery or stale task.",
                deploy_id, service.status,
            )
            return None

        # Also refuse if the deploy row is already RUNNING — means a
        # previous task picked it up.
        if deploy.status == DeploymentStatusChoices.RUNNING:
            logger.info(
                "run_db_deploy: skipping deploy=%s — deploy already RUNNING. "
                "Duplicate delivery.",
                deploy_id,
            )
            return None

        now = timezone.now()
        service.status = SERVICE_STATUS_CHOICES.DEPLOYING
        service.deploy_started = now
        service.save(update_fields=["status", "deploy_started"])

        deploy.status = DeploymentStatusChoices.RUNNING
        deploy.started_at = now
        deploy.stage = "starting"
        deploy.progress = 5
        deploy.status_message = "Database deployment in progress."
        deploy.save(update_fields=[
            "status", "started_at", "stage", "progress", "status_message",
        ])
        return deploy, service


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=20,
    name="deployments.celery.tasks.run_db_deploy",
)
def run_db_deploy(self, deploy_id: str | int) -> None:
    """Execute a database-platform deployment via DBDeployer."""
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
            deploy, service,
            "Deployment cancelled before execution.",
            stage="cancelled",
        )
        Service.objects.filter(pk=service.pk).update(
            status=SERVICE_STATUS_CHOICES.STOPPED,
            task_id=None, deploy_started=None,
        )
        return

    cfg = _build_db_cfg(deploy, service)

    errors = validate_db_config(platform, cfg)
    if errors:
        safe_keys = sorted(str(k) for k in cfg.keys())
        logger.warning(
            "DB validation failed for deploy=%s platform=%s config_keys=%s errors=%s",
            deploy.pk, platform, safe_keys, errors,
        )
        msg = "DB config validation failed: " + "; ".join(errors)
        _mark_failure(
            deploy, service, msg, stage="validation",
            details={"errors": errors, "config_keys": safe_keys},
        )
        return

    _create_deploy_log(
        deploy, stage="validation",
        message=f"Config validated for platform '{platform}'.",
        progress=10,
        details={"platform": platform, "container": container_name},
    )

    event_sink = None
    try:
        try:
            from deployments.core.sink import DBAndChannelEventSink
        except ImportError:
            from deploy.sink import DBAndChannelEventSink  # type: ignore
        event_sink = DBAndChannelEventSink(deploy.pk)
    except Exception:
        logger.exception("Event sink unavailable for deploy %s", deploy.pk)

    # Acquire the per-service advisory lock so duplicate delivery of
    # this task cannot race with itself even if the row-lock check above
    # somehow passes (e.g. the original task crashed after releasing
    # the row but before completing Docker work).
    try:
        with acquire_service_deployment_lock(service.pk):
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
            deploy.pk, container_name,
        )
        # Use the unified retryability predicate.
        if (
            self.request.retries < self.max_retries
            and is_retryable_exception(
                exc,
                recoverable_types=(DeploymentError,),
                transient_markers=(
                    "timeout", "connection", "temporarily", "unavailable",
                    "network", "docker", "apierror", "servererror",
                ),
            )
        ):
            logger.warning(
                "Retrying run_db_deploy (attempt %s) for deploy=%s: %s",
                self.request.retries + 1, deploy.pk, exc,
            )
            raise self.retry(exc=exc)

        _mark_failure(
            deploy, service,
            str(exc) or "Unexpected error during database deployment.",
            stage=getattr(exc, "stage", "deployment_failed"),
            details={"error": str(exc)}, tb=tb,
        )
        return

    if result.success:
        _mark_success(deploy, service, result.message)
    else:
        _mark_failure(
            deploy, service,
            result.message or result.error or "Database deployment failed.",
            stage="deployment_failed",
            details=result.details or {},
        )
