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
import uuid
from typing import Any

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from core.global_settings.config import SERVICE_STATUS_CHOICES  # type: ignore
from deploy.models import BuildCacheArtifact, BaseRuntimeImage, Deploy, DeploymentStatusChoices  # type: ignore
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
    to_deployment_error,
)
from deployments.common.retry import is_retryable_exception
from deployments.core.state.locks import acquire_service_deployment_lock
from deployments.core.state.manager import StateManager
from services.models import Service  # type: ignore
from services.revisioning import ensure_revision_for_deploy, materialize_revision_config, activate_revision_locked, mark_revision_failed, get_active_deploy

from .services.deploy_service import DeployService
from .services.stop_service import StopService
from .schedules import monitor_services  # noqa: F401  — re-export for beat

logger = logging.getLogger(__name__)


# ===========================================================================
# App deploy / stop
# ===========================================================================

@shared_task(name="deployments.celery.tasks.expire_idle_shell_sessions")
def expire_idle_shell_sessions_task() -> dict:
    """Expire restricted shell sessions that have exceeded the operator idle timeout."""
    from services.shell import expire_idle_sessions
    count = expire_idle_sessions()
    logger.info("Expired %s idle restricted shell sessions", count)
    return {"status": "ok", "expired": count}


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
        DeployService().execute(deploy_id, task_id=str(self.request.id))
    except (InvalidServiceStateError, DeploymentValidationError,
            OrchestratorDeploymentError, ContainerTimeoutError):
        # These are permanent deployment failures. The DB deployment state has
        # already been terminalized by DeployService; re-raise so Celery records
        # the task as FAILED and Ready App link_error handlers can run.
        logger.exception("Deployment did not complete for deploy_id: %s", deploy_id)
        raise
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
        raise
    except Exception as exc:
        # Unknown Python exceptions are platform bugs by default, not
        # transient deployment failures.  Translate them at the worker
        # boundary so NameError/AttributeError/KeyError/internal invariant
        # failures do not cause repeated deploy attempts.  Explicitly
        # recoverable DeploymentError subclasses are handled above.
        if Deploy.objects.filter(pk=deploy_id, cancel_requested=True).exists():
            logger.info("Deploy %s was cancelled while failing; suppressing retry.", deploy_id)
            return
        translated = to_deployment_error(exc, stage="deployment")
        logger.exception(
            "Non-recoverable deployment exception for deploy_id=%s: code=%s technical=%s",
            deploy_id, translated.code, translated.technical_message,
        )
        raise translated from exc


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def stop(self, service_id, expected_lifecycle_generation=None) -> None:
    logger.info(
        "Initializing stop for service_id: %s expected_lifecycle_generation=%s",
        service_id,
        expected_lifecycle_generation,
    )
    try:
        StopService().execute(
            service_id,
            expected_lifecycle_generation=expected_lifecycle_generation,
        )
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


@shared_task(bind=True, max_retries=3, default_retry_delay=10, name="deployments.celery.tasks.restart_service")
def restart_service(self, service_id) -> None:
    """Restart a running application through the selected runtime backend."""
    try:
        service = Service.objects.get(pk=service_id)
        from deployments.infrastructure.django_runtime import DjangoRuntimeSelectionResolver
        selection = DjangoRuntimeSelectionResolver().resolve(service=service, probe=False)
        if selection.backend == "swarm":
            runtime = DjangoRuntimeSelectionResolver().registry.resolve_adapter(selection)
            runtime.restart_service_group(str(service.pk))
            StateManager.transition_service(
                service.pk,
                SERVICE_STATUS_CHOICES.RUNNING,
                update_fields={
                    "desired_state": "running",
                    "task_id": None,
                    "deploy_started": None,
                    "deployed_at": timezone.now(),
                },
            )
            logger.info("Restarted runtime service group for service=%s", service_id)
            return

        # Legacy fallback keeps the existing deploy semantics.
        from deployments.celery.services.stop_service import StopService
        StopService().execute(str(service.pk))
        deploy_item = get_active_deploy(service)
        if deploy_item is None:
            raise InvalidServiceStateError("Service has no active deployment.")
        StateManager.transition_deploy(
            deploy_item.pk,
            DeploymentStatusChoices.PENDING,
            update_fields={
                "stage": "queued",
                "progress": 0,
                "status_message": "Restart queued.",
            },
        )
        DeployService().execute(str(deploy_item.pk), task_id=str(self.request.id))
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        logger.exception("Restart exhausted retries for service=%s", service_id)

@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def _mark_base_image_retry_pending(base_image_id, task_id: str, exc: Exception) -> None:
    row = BaseRuntimeImage.objects.filter(pk=base_image_id).values(
        "build_task_id", "last_error_details", "image_ref"
    ).first()
    if not row or str(row.get("build_task_id") or "") != str(task_id):
        logger.info(
            "Ignoring retry-pending state from superseded base-image task id=%s base=%s",
            task_id, base_image_id,
        )
        return
    details = dict(row.get("last_error_details") or {})
    details.update({
        "stage": "base_image",
        "exception_type": type(exc).__name__,
        "technical_message": str(exc) or type(exc).__name__,
        "retry_pending": True,
        "base_image_ref": row.get("image_ref") or "",
        "resource_policy_source": "server_owned",
    })
    BaseRuntimeImage.objects.filter(
        pk=base_image_id,
        status=BaseRuntimeImage.Status.BUILDING,
        build_task_id=str(task_id),
    ).update(
        build_completed_at=None,
        last_error=str(exc),
        last_error_details=details,
        updated_at=timezone.now(),
    )

def _mark_base_image_terminal_failure(base_image_id, task_id: str, exc: Exception) -> None:
    current = (
        BaseRuntimeImage.objects.filter(pk=base_image_id)
        .values("image_ref", "last_error_details")
        .first()
        or {}
    )
    details = dict(current.get("last_error_details") or {})
    details.update({
        "stage": "base_image",
        "exception_type": type(exc).__name__,
        "technical_message": str(exc) or type(exc).__name__,
        "retry_pending": False,
        "base_image_ref": current.get("image_ref") or "",
        "resource_policy_source": "server_owned",
    })
    updated = BaseRuntimeImage.objects.filter(
        pk=base_image_id,
        status=BaseRuntimeImage.Status.BUILDING,
        build_task_id=str(task_id),
    ).update(
        status=BaseRuntimeImage.Status.FAILED,
        build_task_id="",
        build_owner_deployment_id="",
        last_error=str(exc),
        last_error_details=details,
        build_completed_at=timezone.now(),
        updated_at=timezone.now(),
    )
    if not updated:
        logger.info(
            "Ignoring terminal base-image failure from superseded task id=%s base=%s",
            task_id,
            base_image_id,
        )

@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def build_base_runtime_image(self, base_image_id, force_rebuild=False, build_policy=None) -> None:
    """Build/rebuild one registered operator base runtime image.

    Resource limits use the same server-owned policy contract as application
    image builds. force_rebuild is a build option, never a resource-policy field.
    """
    from deploy.base_images import build_registered_base_image
    from deployments.common.resource_policy import resolve_build_policy

    try:
        effective_policy = resolve_build_policy(build_policy)
    except (TypeError, ValueError) as exc:
        _mark_base_image_terminal_failure(base_image_id, str(self.request.id), exc)
        logger.exception(
            "Base image resource-policy construction failed id=%s: %s",
            base_image_id,
            exc,
        )
        raise

    try:
        build_registered_base_image(
            base_image_id,
            task_id=str(self.request.id),
            force_rebuild=bool(force_rebuild),
            build_policy=effective_policy,
        )
    except Exception as exc:
        if isinstance(exc, TimeoutError):
            _mark_base_image_terminal_failure(base_image_id, str(self.request.id), exc)
            logger.exception(
                "Base image build reached its dedicated lifecycle deadline id=%s: %s",
                base_image_id,
                exc,
            )
            raise
        if self.request.retries < self.max_retries:
            _mark_base_image_retry_pending(base_image_id, str(self.request.id), exc)
            logger.warning(
                "Base image build failed; retrying id=%s attempt=%d/%d: %s",
                base_image_id,
                self.request.retries + 1,
                self.max_retries + 1,
                exc,
            )
            raise self.retry(exc=exc)

        _mark_base_image_terminal_failure(base_image_id, str(self.request.id), exc)
        logger.exception(
            "Base image build exhausted retries id=%s: %s",
            base_image_id,
            exc,
        )
        raise

@shared_task(bind=True, max_retries=0, name="deployments.celery.tasks.dispatch_deployment_event_outbox")
def dispatch_deployment_event_outbox(self, batch_size=100) -> dict[str, int]:
    """Project durable deployment events without making projection authoritative."""
    from deployments.common.event_outbox import dispatch_pending
    return dispatch_pending(batch_size=batch_size)

@shared_task(bind=True, max_retries=0, name="deployments.celery.tasks.prune_deployment_event_outbox")
def prune_deployment_event_outbox(self, retention_days=None, batch_size=1000):
    """Prune only already-dispatched deployment events past retention."""
    from deployments.common.event_outbox import prune_dispatched

    if retention_days is None:
        import os
        retention_days = int(os.environ.get("DEPLOYMENT_EVENT_OUTBOX_RETENTION_DAYS", "30"))
    return {"deleted": prune_dispatched(older_than_days=retention_days, batch_size=batch_size)}

@shared_task(bind=True, max_retries=0, name="deployments.celery.tasks.maintain_build_cache")
def maintain_build_cache(self, force=False) -> dict[str, object]:
    """Reconcile tenant application-image retention and global BuildKit GC."""
    from deploy.build_cache import (
        build_cache_policy,
        enforce_service_cache_quota,
        enforce_user_cache_quota,
        prune_global_build_cache,
    )
    policy = build_cache_policy()
    if not policy["enabled"] and not force:
        return {"status": "disabled"}

    service_ids = (
        BuildCacheArtifact.objects.filter(reclaimed_at__isnull=True)
        .values_list("service_id", flat=True)
        .distinct()
    )
    user_ids = (
        BuildCacheArtifact.objects.filter(reclaimed_at__isnull=True)
        .values_list("user_id", flat=True)
        .distinct()
    )
    service_results = [
        enforce_service_cache_quota(str(service_id))
        for service_id in service_ids.iterator()
    ]
    user_results = [
        enforce_user_cache_quota(str(user_id))
        for user_id in user_ids.iterator()
    ]
    global_result = prune_global_build_cache(force=bool(force))
    return {
        "status": global_result.get("status", "ok"),
        "services": len(service_results),
        "users": len(user_results),
        "tenant_removed": sum(
            int(item.get("removed", 0))
            for item in service_results + user_results
        ),
        "tenant_reclaimed_bytes": sum(
            int(item.get("reclaimed_bytes", 0))
            for item in service_results + user_results
        ),
        "global": global_result,
    }


@shared_task(bind=True, max_retries=0, name="deployments.celery.tasks.reclaim_released_volumes")
def reclaim_released_volumes(self, batch_size=100) -> dict[str, int]:
    """Reclaim expired released volumes without hiding physical storage state."""
    from datetime import timedelta
    import docker.errors
    from services.models import Volume as RegistryVolume
    from deployments.core.manager.volume_manager import Volume as DockerVolume
    from core.settings_service import volume_release_retention_days

    retention_days = volume_release_retention_days()
    cutoff = timezone.now() - timedelta(days=retention_days)
    try:
        limit = max(1, min(int(batch_size), 1000))
    except (TypeError, ValueError):
        limit = 100

    candidates = list(
        RegistryVolume.objects.filter(
            service__isnull=True,
            released_at__isnull=False,
            released_at__lte=cutoff,
        ).order_by("released_at").values_list("pk", flat=True)[:limit]
    )

    reclaimed = failed = skipped = 0

    for volume_id in candidates:
        with transaction.atomic():
            row = (
                RegistryVolume.objects.select_for_update()
                .filter(
                    pk=volume_id,
                    service__isnull=True,
                    released_at__isnull=False,
                    released_at__lte=cutoff,
                )
                .first()
            )
            if row is None:
                skipped += 1
                continue

            row.reclaim_attempted_at = timezone.now()
            row.reclaim_error = ""
            row.save(update_fields=[
                "reclaim_attempted_at", "reclaim_error", "updated_at",
            ])
            docker_name = row.get_docker_volume_name()

            try:
                docker_volume = DockerVolume(docker_name)
                try:
                    raw_volume = docker_volume.client.volumes.get(docker_name)
                except docker.errors.NotFound:
                    raw_volume = None

                if raw_volume is not None:
                    labels = dict((getattr(raw_volume, "attrs", {}) or {}).get("Labels") or {})
                    if labels.get("managed-by") != "django-paas-deployer":
                        raise RuntimeError(
                            f"Refusing to reclaim Docker volume {row.name!r}: "
                            "ownership label is missing or unexpected."
                        )
                    docker_volume.remove()
                    try:
                        docker_volume.client.volumes.get(docker_name)
                    except docker.errors.NotFound:
                        pass
                    else:
                        raise RuntimeError(
                            f"Docker volume {docker_name!r} still exists after reclaim."
                        )

                # pre_delete safely observes an already-absent Docker volume.
                row.delete()
                reclaimed += 1
            except Exception as exc:
                failed += 1
                RegistryVolume.objects.filter(pk=row.pk).update(
                    reclaim_error=f"{type(exc).__name__}: {exc}",
                    updated_at=timezone.now(),
                )
                logger.exception(
                    "Released volume reclaim failed volume=%s docker=%s",
                    row.pk,
                    docker_name,
                )

    return {
        "retention_days": retention_days,
        "candidates": len(candidates),
        "reclaimed": reclaimed,
        "failed": failed,
        "skipped": skipped,
    }


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
    """Create/reuse registry-backed persistent DB storage or fail deployment.

    Database data is persistent by contract. A quota or provisioning failure
    must never fall back to an anonymous Docker volume.
    """
    p = str(platform or "").lower().strip()
    if p not in _DB_DEFAULT_DATA_PATHS:
        return None
    default_bind, default_size_mb = _DB_DEFAULT_DATA_PATHS[p]

    from services.models import Volume

    existing = Volume.objects.filter(service_id=service.pk).order_by("created_at").first()
    if existing is not None:
        return {
            "source": existing.get_docker_volume_name(),
            "target": (
                (existing.service_attachments or {}).get(str(service.pk), {}).get("bind")
                or existing.default_bind
                or default_bind
            ),
            "mode": (existing.service_attachments or {}).get(str(service.pk), {}).get("mode")
            or existing.default_mode or "rw",
        }

    ok, msg = service.can_allocate_storage(default_size_mb)
    size_mb = default_size_mb
    if not ok:
        remaining = max(0, int(service.get_remaining_storage_mb()))
        if remaining >= 128:
            size_mb = remaining
            logger.info(
                "DB default volume for service %s reduced from %d MB to %d MB to fit logical quota.",
                service.pk, default_size_mb, size_mb,
            )
        else:
            from deployments.common.exceptions import DeploymentValidationError
            raise DeploymentValidationError(
                f"Persistent database storage requires {default_size_mb} MB but service {service.pk} has only {remaining} MB remaining.",
                stage="volume_creation",
                details={
                    "service_id": str(service.pk),
                    "requested_mb": default_size_mb,
                    "remaining_mb": remaining,
                    "quota_error": msg,
                    "persistence_required": True,
                },
            )

    base = getattr(service, "get_docker_service_name", lambda: "")() or f"svc-{service.pk}"
    base_clean = "".join(c if c.isalnum() else "-" for c in str(base)).strip("-") or f"svc-{service.pk}"
    name = (base_clean[:24] + "-data")[:32]
    try:
        volume = Volume.objects.create(
            name=name,
            user=service.user,
            service=service,
            service_attachments={str(service.pk): {"bind": default_bind, "mode": "rw"}},
            default_bind=default_bind,
            default_mode="rw",
            size_mb=size_mb,
        )
    except Exception as exc:
        raise DeploymentValidationError(
            "Persistent database storage could not be registered for this service.",
            stage="volume_creation",
            details={
                "service_id": str(service.pk),
                "requested_mb": size_mb,
                "exception_type": type(exc).__name__,
                "technical_message": str(exc),
                "persistence_required": True,
            },
        ) from exc

    logger.info(
        "Auto-created managed DB volume '%s' (%d MB) for service %s platform=%s.",
        volume.name, size_mb, service.pk, p,
    )
    return {
        "source": volume.get_docker_volume_name(),
        "target": default_bind,
        "mode": "rw",
    }

def _build_db_cfg(deploy: Deploy, service: Service) -> dict[str, Any]:
    """Build DB runtime config from the immutable ServiceRevision."""
    revision_cfg = materialize_revision_config(deploy.revision) if getattr(deploy, "revision_id", None) else parse_config(getattr(deploy, "config", None))
    cfg: dict[str, Any] = dict(revision_cfg or {})

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

    public_db = bool(cfg.get("public") or cfg.get("public_host") or cfg.get("expose_public"))
    if public_db:
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
        from deployments.core.sink import DBAndChannelEventSink
        from deployments.core.types import DeploymentEvent

        event_details = dict(details or {})
        event_details["event_type"] = event_type
        if exception_type:
            event_details["exception_type"] = exception_type
        if traceback_str:
            event_details["traceback"] = traceback_str

        DBAndChannelEventSink(deploy.pk)(
            DeploymentEvent(
                stage=stage,
                message=message,
                level=level,
                progress=progress,
                details=event_details,
            )
        )
    except Exception:
        logger.exception(
            "Failed to write DeployLog for deploy %s stage=%s", deploy.pk, stage
        )


def _mark_success(deploy: Deploy, service: Service, result_message: str, *, task_id: str | None = None) -> None:
    message = result_message or "Database deployed successfully."
    event_payload = {
        "event_id": str(uuid.uuid4()),
        "trace_id": str(deploy.pk),
        "deployment_id": str(deploy.pk),
        "service_id": str(deploy.service_id),
        "revision_id": str(getattr(deploy, "revision_id", "") or ""),
        "task_id": str(task_id or "system"),
        "event_type": "deployment.finished.info",
        "stage": "finished",
        "level": "info",
        "message": message,
        "progress": 100,
        "details": {"runtime": "database", "controlled_by": "db_deployer"},
    }

    committed = StateManager.activate_revision_and_succeed(
        deploy.pk,
        deploy.revision_id,
        task_id=task_id,
        update_fields={
            "stage": "finished",
            "progress": 100,
            "status_message": message,
            "error_message": "",
        },
        event_payload=event_payload,
    )
    if not committed:
        logger.info("Ignoring stale/cancelled DB deploy success for deploy=%s", deploy.pk)
        return

    logger.info("DB deploy succeeded: deploy=%s service=%s", deploy.pk, service.pk)


def _mark_failure(
    deploy: Deploy, service: Service, message: str, *,
    stage: str = "deployment_failed",
    details: dict | None = None, tb: str = "", task_id: str | None = None,
) -> None:
    event_details = {
        "runtime": "database",
        "controlled_by": "db_deployer",
        **dict(details or {}),
    }
    if tb:
        event_details["traceback"] = tb

    event_payload = {
        "event_id": str(uuid.uuid4()),
        "trace_id": str(deploy.pk),
        "deployment_id": str(deploy.pk),
        "service_id": str(deploy.service_id),
        "revision_id": str(getattr(deploy, "revision_id", "") or ""),
        "task_id": str(task_id or "system"),
        "event_type": f"deployment.{stage}.error",
        "stage": stage,
        "level": "error",
        "message": message,
        "progress": 100,
        "details": event_details,
    }

    committed = (
        StateManager.transition_deploy_terminal_if_owned(
            deploy.pk,
            DeploymentStatusChoices.FAILED,
            task_id=task_id,
            update_fields={
                "stage": stage,
                "error_message": message,
                "status_message": "Database deployment failed.",
            },
            event_payload=event_payload,
        )
        if task_id
        else StateManager.transition_deploy_system_terminal(
            deploy.pk,
            DeploymentStatusChoices.FAILED,
            update_fields={
                "stage": stage,
                "error_message": message,
                "status_message": "Database deployment failed.",
            },
            event_payload=event_payload,
        )
    )

    if not committed:
        logger.info("Ignoring stale/unowned DB deploy failure for deploy=%s", deploy.pk)
        return

    if getattr(deploy, "revision_id", None):
        try:
            mark_revision_failed(deploy.revision_id)
        except Exception:
            logger.exception("Failed to mark DB revision %s as failed", deploy.revision_id)

    if service.status not in (SERVICE_STATUS_CHOICES.STOPPED, SERVICE_STATUS_CHOICES.FAILED):
        StateManager.transition_service(
            service.pk,
            SERVICE_STATUS_CHOICES.FAILED,
            update_fields={"deploy_started": None, "task_id": None},
        )

    logger.warning(
        "DB deploy failed: deploy=%s service=%s stage=%s msg=%s",
        deploy.pk, service.pk, stage, message,
    )



def _lock_for_db_deploy(
    deploy_id: str | int,
    *,
    task_id: str | None = None,
    allow_owned_retry: bool = False,
) -> tuple[Deploy, Service] | None:
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

        expected_owner = str(task_id or "")
        if expected_owner and deploy.execution_task_id not in ("", expected_owner):
            logger.info("run_db_deploy: skipping deploy=%s — stale task owner %s (current=%s)", deploy_id, expected_owner, deploy.execution_task_id)
            return None
        if expected_owner and service.task_id not in (None, "", expected_owner):
            logger.info("run_db_deploy: skipping deploy=%s — service task owner mismatch", deploy_id)
            return None

        # Normal deliveries are allowed to claim only QUEUED work. A Celery
        # retry is different: it reuses the same task id and must be allowed to
        # resume the RUNNING deployment it already owns. Fresh duplicate task
        # deliveries still fail this ownership check and are ignored.
        owned_retry = (
            allow_owned_retry
            and service.status == SERVICE_STATUS_CHOICES.DEPLOYING
            and deploy.status == DeploymentStatusChoices.RUNNING
            and expected_owner
            and deploy.execution_task_id == expected_owner
            and service.task_id == expected_owner
        )
        if owned_retry:
            deploy.refresh_from_db()
            return deploy, service

        if service.status != SERVICE_STATUS_CHOICES.QUEUED:
            logger.info(
                "run_db_deploy: skipping deploy=%s — service status is %s "
                "(expected QUEUED). Duplicate delivery or stale task.",
                deploy_id, service.status,
            )
            return None

        if deploy.status == DeploymentStatusChoices.RUNNING:
            logger.info(
                "run_db_deploy: skipping deploy=%s — deploy already RUNNING. "
                "Duplicate delivery.",
                deploy_id,
            )
            return None

        now = timezone.now()
        StateManager.transition_service(
            service.pk, SERVICE_STATUS_CHOICES.DEPLOYING,
            update_fields={"deploy_started": now, "task_id": str(task_id or "")},
        )
        deploy.execution_task_id = str(task_id) if task_id else ""
        StateManager.transition_deploy(
            deploy.pk, DeploymentStatusChoices.RUNNING,
            update_fields={
                "started_at": now, "worker_heartbeat_at": now,
                "execution_task_id": str(task_id or ""),
                "stage": "starting", "progress": 5,
                "status_message": "Database deployment in progress.",
            },
        )
        deploy.refresh_from_db()
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

    locked = _lock_for_db_deploy(
        deploy_id,
        task_id=str(self.request.id),
        allow_owned_retry=bool(getattr(self.request, "retries", 0)),
    )
    if locked is None:
        return

    deploy, service = locked
    deploy = ensure_revision_for_deploy(deploy)
    deploy.refresh_from_db(fields=["revision"])
    service = Service.objects.select_related("plan", "network").get(pk=service.pk)
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
        StateManager.transition_service(
            service.pk, SERVICE_STATUS_CHOICES.STOPPED,
            update_fields={"task_id": None, "deploy_started": None},
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
                service_id=str(service.pk),
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
            details={"error": str(exc)}, tb=tb, task_id=str(self.request.id),
        )
        return

    if result.success:
        _mark_success(deploy, service, result.message, task_id=str(self.request.id))
    else:
        failure_message = (
            result.message
            or result.error
            or "Database deployment failed."
        )
        result_details = result.details or {}

        # A registry/Docker pull failure can be transient (for example mirror
        # DNS timeout or HTTP 5xx). Retry only when the normalized result says
        # it is safe to do so. The owned-retry path above permits the same
        # Celery task to resume the RUNNING Deploy without admitting duplicates.
        if (
            bool(result_details.get("retryable"))
            and self.request.retries < self.max_retries
        ):
            logger.warning(
                "Retrying transient DB deployment failure for deploy=%s on attempt %s/%s: %s",
                deploy.pk,
                self.request.retries + 1,
                self.max_retries,
                failure_message,
            )
            retry_error = DeploymentError(
                failure_message,
                stage=str(result_details.get("stage") or "image_pull"),
                code=str(result_details.get("reason_code") or "DATABASE_DEPLOYMENT_TRANSIENT_FAILURE").upper(),
                category="transient_infrastructure",
                recoverable=True,
                user_message=failure_message,
                details=result_details,
            )
            raise self.retry(exc=retry_error, countdown=self.default_retry_delay)

        _mark_failure(
            deploy,
            service,
            failure_message,
            stage=str(result_details.get("stage") or "deployment_failed"),
            details=result_details,
        )
        # Celery's success callback is the coordinator's "dependency succeeded"
        # signal. A DB deployment that returned a terminal failure result must
        # therefore fail at the task boundary so link_error invokes
        # application_service_failed instead of advance_application_service.
        raise DeploymentError(
            failure_message,
            stage=str(result_details.get("stage") or "deployment_failed"),
            code="DATABASE_DEPLOYMENT_FAILED",
            user_message=failure_message,
            details=result_details,
        )
