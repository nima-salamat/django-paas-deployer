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
            cfg = parse_config(deploy_item.config)
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
        # A cancelled deployment must never be resurrected by Celery retry
        # handling after the API has already made the state terminal.
        if Deploy.objects.filter(pk=deploy_id, cancel_requested=True).exists():
            logger.info("Deploy %s is already cancelled; skipping worker execution.", deploy_id)
            return
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
        # Never retry a deployment that the operator cancelled while the
        # worker was unwinding (for example after SIGTERM/revoke).
        if Deploy.objects.filter(pk=deploy_id, cancel_requested=True).exists():
            logger.info("Deploy %s was cancelled while failing; suppressing retry.", deploy_id)
            return
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


@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def build_base_runtime_image(self, base_image_id) -> None:
    """Build/rebuild one registered operator base runtime image.

    This runs independently from an application's deployment task so a user
    force-cancelling that deployment cannot terminate a shared base build.
    """
    from deploy.base_images import build_registered_base_image
    try:
        build_registered_base_image(base_image_id, task_id=str(self.request.id))
    except Exception as exc:
        if self.request.retries < self.max_retries:
            logger.warning("Base image build failed; retrying id=%s: %s", base_image_id, exc)
            raise self.retry(exc=exc)
        logger.exception("Base image build exhausted retries id=%s", base_image_id)



# ===========================================================================
# DB deploy helpers
# ===========================================================================

def _resolve_platform(deploy: Deploy) -> str:
    """config.platform -> service.plan.platform -> empty string."""
    # The Service Plan is the execution authority. Tenant config cannot
    # switch a deployment into another platform family (especially DB).
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
        # Prefer the Docker volume name (vol-{id}-{name}), matching
        # deploy_service / signals.  Fall back to the human name only if
        # the helper is missing.
        getter = getattr(vol, "get_docker_volume_name", None)
        if callable(getter):
            try:
                name = getter()
            except Exception:
                name = getattr(vol, "name", None)
        else:
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


# ---------------------------------------------------------------------------
# Default-data-volume auto-creation for DB deploys
# ---------------------------------------------------------------------------
#
# When a database service has NO Volume attached in the Django registry
# (the user's PostgreSQL), the deploy would otherwise fall back to an
# anonymous Docker volume — which works, but loses all data the moment the
# container is removed (rebuild, host reboot, etc.).
#
# To prevent silent data loss, every DB deploy now auto-creates a named
# Volume record in the Django registry (services.Volume) AND binds it to
# the platform's data directory.  The Volume is owned exclusively by the
# service (FK + service_attachments), respects the plan's max_storage
# quota, and is reused on subsequent deploys.

# Platform → (container data path, default size in MB)
_DB_DEFAULT_DATA_PATHS: dict[str, tuple[str, int]] = {
    "mysql":      ("/var/lib/mysql",           1024),
    "mariadb":    ("/var/lib/mysql",           1024),
    "postgresql": ("/var/lib/postgresql/data", 1024),
    "postgres":   ("/var/lib/postgresql/data", 1024),
    "mongodb":    ("/data/db",                 2048),
    "mongo":      ("/data/db",                 2048),
    "redis":      ("/data",                     256),
    "oracle":     ("/opt/oracle/oradata",      2048),
}


def _ensure_default_db_volume(platform: str, service: Service) -> dict | None:
    """
    Guarantee a DB service has a named Volume in the Django registry for
    its platform-specific data directory.  Returns a volume-bind dict
    ``{"source": name, "target": bind, "mode": "rw"}`` suitable for
    ``cfg["volumes"]``, or ``None`` if creation failed (non-fatal — the
    deploy will still proceed with an anonymous Docker volume).

    Idempotent: if the service already owns a Volume, returns that one.
    Respects the service plan's max_storage quota — if the default size
    would exceed the remaining quota, shrinks to fit; if even 128 MB
    won't fit, skips creation and logs a warning.
    """
    p = str(platform or "").lower().strip()
    if p not in _DB_DEFAULT_DATA_PATHS:
        return None
    default_bind, default_size_mb = _DB_DEFAULT_DATA_PATHS[p]

    # ------------------------------------------------------------------
    # 1. If the service already owns a Volume, reuse it.
    # ------------------------------------------------------------------
    try:
        from services.models import Volume  # type: ignore
    except Exception:
        logger.debug(
            "services.models.Volume unavailable; cannot auto-create volume "
            "for service %s", service.pk, exc_info=True,
        )
        return None

    existing = None
    rel = getattr(service, "volumes", None)
    if rel is not None and hasattr(rel, "all"):
        try:
            existing = rel.all().first()
        except Exception:
            logger.exception(
                "service.volumes.all() lookup failed for service %s", service.pk
            )
    if existing is None:
        try:
            from django.db.models import Q
            existing = (
                Volume.objects
                .filter(Q(service_id=service.pk))
                .order_by("created_at")
                .first()
            )
        except Exception:
            logger.debug(
                "Volume registry query failed for service %s; skipping",
                service.pk, exc_info=True,
            )

    if existing is not None:
        # Reuse — prefer the attachment bind, fall back to default_bind.
        atts = getattr(existing, "service_attachments", None) or {}
        att = atts.get(str(service.pk), {}) if isinstance(atts, dict) else {}
        bind = att.get("bind") or getattr(existing, "default_bind", "") or default_bind
        return {
            "source": (
                existing.get_docker_volume_name()
                if hasattr(existing, "get_docker_volume_name")
                else existing.name
            ),
            "target": bind,
            "mode": att.get("mode") or getattr(existing, "default_mode", "") or "rw",
        }

    # ------------------------------------------------------------------
    # 2. No existing Volume — create one.  First check the plan quota.
    # ------------------------------------------------------------------
    size_mb = default_size_mb
    plan = getattr(service, "plan", None)
    if plan is not None and hasattr(plan, "can_allocate_storage"):
        try:
            # Try the requested size first, then shrink to fit.
            ok, _ = plan.can_allocate_storage(size_mb)
            if not ok:
                # Shrink to the remaining quota, but not below 128 MB.
                remaining = getattr(plan, "get_remaining_storage_mb", lambda: 0)()
                try:
                    remaining = int(remaining)
                except (TypeError, ValueError):
                    remaining = 0
                if remaining >= 128:
                    size_mb = remaining
                    logger.info(
                        "Plan quota for service %s is tight; auto-volume "
                        "shrunk to %d MB (default was %d MB).",
                        service.pk, size_mb, default_size_mb,
                    )
                else:
                    logger.warning(
                        "Service %s plan has only %d MB remaining; cannot "
                        "auto-create a default DB volume. The deploy will "
                        "use an anonymous Docker volume and data will NOT "
                        "persist across container removals.",
                        service.pk, remaining,
                    )
                    return None
        except Exception:
            logger.exception(
                "Plan quota check failed for service %s; attempting "
                "auto-volume creation anyway with default size.",
                service.pk,
            )

    # ------------------------------------------------------------------
    # 3. Derive a unique Docker volume name (≤32 chars per model).
    # ------------------------------------------------------------------
    base = getattr(service, "get_docker_service_name", lambda: "")() or f"svc-{service.pk}"
    # Strip non-alphanumerics (Docker volume names allow [A-Za-z0-9_.-]
    # but the Django Volume.name field is CharField(32, unique=True)).
    base_clean = "".join(c if c.isalnum() else "-" for c in str(base)).strip("-")
    if not base_clean:
        base_clean = f"svc-{service.pk}"
    suffix = "-data"
    max_base_len = 32 - len(suffix)
    vol_name = (base_clean[:max_base_len] + suffix)[:32]

    # Ensure uniqueness without truncating past 32 chars.
    try:
        existing_by_name = Volume.objects.filter(name=vol_name).first()
    except Exception:
        existing_by_name = None
    if existing_by_name is not None:
        # Append a short pk suffix to disambiguate.
        suffix2 = f"-{str(service.pk)[-6:]}"
        max_base_len2 = 32 - len(suffix2)
        vol_name = (base_clean[:max_base_len2] + suffix2)[:32]

    # ------------------------------------------------------------------
    # 4. Create the Volume record in the Django registry (PostgreSQL).
    # ------------------------------------------------------------------
    user = getattr(service, "user", None)
    if user is None:
        logger.warning(
            "Service %s has no owner user; cannot auto-create Volume.", service.pk
        )
        return None

    try:
        with transaction.atomic():
            vol = Volume.objects.create(
                name=vol_name,
                user=user,
                service=service,
                service_attachments={
                    str(service.pk): {"bind": default_bind, "mode": "rw"}
                },
                default_bind=default_bind,
                default_mode="rw",
                size_mb=size_mb,
            )
        logger.info(
            "Auto-created Volume '%s' (%d MB, bind=%s) for service %s "
            "platform=%s — DB data will now persist across rebuilds.",
            vol_name, size_mb, default_bind, service.pk, p,
        )
    except Exception as exc:
        logger.warning(
            "Could not auto-create Volume '%s' for service %s: %s. "
            "Deploy will proceed with an anonymous Docker volume; data "
            "will NOT persist across container removals.",
            vol_name, service.pk, exc,
        )
        return None

    return {
        "source": (
            vol.get_docker_volume_name()
            if hasattr(vol, "get_docker_volume_name")
            else vol.name
        ),
        "target": default_bind,
        "mode": "rw",
    }


def _build_db_cfg(deploy: Deploy, service: Service) -> dict[str, Any]:
    """Merge Deploy.config credentials with live Service metadata."""
    cfg: dict[str, Any] = {}
    cfg.update(parse_config(getattr(deploy, "config", None)))

    platform = _resolve_platform(deploy)
    if platform:
        cfg["platform"] = platform

    if platform in ("mysql", "mariadb"):
        if not str(cfg.get("root_password") or "").strip() and str(cfg.get("password") or "").strip():
            cfg["root_password"] = str(cfg["password"]).strip()
        # If username is set but app password empty, reuse root so MYSQL_PASSWORD
        # is never blank when MYSQL_USER is present.
        if (
            str(cfg.get("username") or "").strip()
            and not str(cfg.get("password") or "").strip()
            and str(cfg.get("root_password") or "").strip()
        ):
            cfg["password"] = str(cfg["root_password"]).strip()
        logger.info(
            "DB cfg built for deploy=%s platform=%s keys=%s "
            "has_root=%s has_password=%s has_user=%s has_db=%s",
            getattr(deploy, "pk", None),
            platform,
            sorted(cfg.keys()),
            bool(str(cfg.get("root_password") or "").strip()),
            bool(str(cfg.get("password") or "").strip()),
            bool(str(cfg.get("username") or "").strip()),
            bool(str(cfg.get("database") or "").strip()),
        )

    plan = getattr(service, "plan", None)
    if plan is not None:
        if cfg.get("max_cpu") is None and getattr(plan, "max_cpu", None) is not None:
            cfg["max_cpu"] = plan.max_cpu
        if cfg.get("max_ram") is None and getattr(plan, "max_ram", None) is not None:
            cfg["max_ram"] = plan.max_ram

    # Networks: always use the Docker-side name from PrivateNetwork
    # (get_docker_network_name → "net-{idhex}-{name}"), same pattern as
    # get_docker_service_name / get_docker_volume_name for containers/volumes.
    # Using PrivateNetwork.name alone does not match the real Docker network
    # and leaves the DB container unreachable from other services.
    networks: list[str] = []
    seen_nets: set[str] = set()

    def _add_net(name: str) -> None:
        n = str(name or "").strip()
        if n and n not in seen_nets:
            seen_nets.add(n)
            networks.append(n)

    for n in cfg.get("networks") or []:
        if isinstance(n, str):
            _add_net(n)
        elif isinstance(n, dict):
            _add_net(n.get("name") or n.get("network") or "")

    net = getattr(service, "network", None)
    if net is not None:
        docker_net = None
        getter = getattr(net, "get_docker_network_name", None)
        if callable(getter):
            try:
                docker_net = getter()
            except Exception:
                logger.exception(
                    "get_docker_network_name failed for service %s network",
                    getattr(service, "pk", None),
                )
        if not docker_net:
            docker_net = getattr(net, "name", None)
        if docker_net:
            # Ensure private network is first so it is the primary DNS domain.
            if docker_net in seen_nets:
                networks.remove(docker_net)
                seen_nets.discard(docker_net)
            networks.insert(0, str(docker_net))
            seen_nets.add(str(docker_net))

    _add_net("proxy_net")
    cfg["networks"] = networks
    logger.info(
        "DB networks for service=%s: %s",
        getattr(service, "pk", None),
        networks,
    )

    if not cfg.get("volumes"):
        vols = _collect_service_volumes(service)
        if vols:
            cfg["volumes"] = vols

    # ------------------------------------------------------------------
    # Auto-volume safety net — if the service has NO Volume attached in
    # the Django registry, create one now so DB data persists across
    # rebuilds instead of being lost to an anonymous Docker volume.
    # See ``_ensure_default_db_volume`` for the full rationale.
    # ------------------------------------------------------------------
    if not cfg.get("volumes") and platform in _DB_DEFAULT_DATA_PATHS:
        auto_vol = _ensure_default_db_volume(platform, service)
        if auto_vol:
            cfg["volumes"] = [auto_vol]

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
def run_db_deploy(self, deploy_id: str | int, force_reinit: bool = False) -> None:
    """Execute a database-platform deployment via DBDeployer.

    Parameters
    ----------
    force_reinit : bool, default False
        If True, wipe every named Docker volume bound to this DB before
        starting, so the database reinitialises from scratch.  Use this
        when a previous deploy failed mid-init and left corrupt data.
    """
    logger.info(
        "run_db_deploy started for deploy_id=%s force_reinit=%s",
        deploy_id, force_reinit,
    )

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

    if force_reinit:
        _create_deploy_log(
            deploy, stage="volume_creation",
            message=(
                "Force-reinit requested — wiping data volumes so the "
                "database will reinitialise from scratch. ALL DATA IN "
                "THE DB VOLUMES WILL BE LOST."
            ),
            progress=15,
            level="warning",
            details={"platform": platform, "container": container_name},
        )

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
                force_reinit=force_reinit,
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
