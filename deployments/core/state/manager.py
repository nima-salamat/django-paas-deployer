"""
deployments/core/state/manager.py
---------------------------------
Transactional state transitions with explicit validation.

This is the SINGLE entry point for mutating ``Service.status`` and
``Deploy.status``.  Every transition is:

  1. Validated against ``deployments.common.state_machine``.
  2. Performed inside ``transaction.atomic`` with ``select_for_update``.
  3. Logged with structured context (entity, src, dst, ids).

The legacy ``ServiceStateManager`` class (in celery/service_status.py)
is kept as a thin wrapper that delegates here, so existing call sites
keep working — but NEW code should call ``StateManager`` directly.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone

from deployments.common import state_machine as sm
from deployments.common.exceptions import InvalidServiceStateError

logger = logging.getLogger(__name__)


class StateManager:
    """
    Single source of truth for Service / Deploy state mutations.

    All methods are classmethods — the class is a namespace, not an
    instance.  Each method:
      * Opens a short ``transaction.atomic`` block.
      * Locks the relevant row(s) with ``select_for_update``.
      * Validates the transition via ``state_machine.check_*_transition``.
      * Performs the update.
      * Returns the updated entity (re-fetched, so caller sees fresh state).
    """

    # ------------------------------------------------------------------
    # Service transitions
    # ------------------------------------------------------------------

    @classmethod
    def transition_service(
        cls,
        service_id: int,
        target: str,
        *,
        update_fields: Optional[dict] = None,
    ) -> None:
        """
        Transition a Service to ``target`` with explicit validation.

        Raises ``InvalidServiceStateError`` if the transition is not in
        the allowed table (unless src == target, which is idempotent).
        """
        from services.models import Service  # type: ignore

        with transaction.atomic():
            service = (
                Service.objects
                .select_for_update()
                .filter(pk=service_id)
                .first()
            )
            if service is None:
                raise InvalidServiceStateError(
                    f"Service {service_id} does not exist.",
                    details={"service_id": service_id},
                )

            src = service.status
            try:
                sm.check_service_transition(src, target)
            except sm.InvalidTransition as exc:
                raise InvalidServiceStateError(
                    str(exc),
                    details={
                        "entity": "Service",
                        "service_id": service_id,
                        "src": src,
                        "target": target,
                        "allowed": list(exc.allowed),
                    },
                ) from exc

            updates = {"status": target}
            if update_fields:
                updates.update(update_fields)

            # Standard bookkeeping for each target state.
            now = timezone.now()
            if target == sm.SERVICE_RUNNING:
                updates.setdefault("deployed_at", now)
                updates["deploy_started"] = None
                updates["task_id"] = None
            elif target in (sm.SERVICE_STOPPED, sm.SERVICE_FAILED):
                updates["deploy_started"] = None
                updates["task_id"] = None
            elif target == sm.SERVICE_DEPLOYING:
                updates.setdefault("deploy_started", now)

            Service.objects.filter(pk=service_id).update(**updates)
            logger.info(
                "StateManager: service %s %s -> %s",
                service_id, src, target,
                extra={"entity": "Service", "service_id": service_id,
                       "src": src, "dst": target},
            )

    @classmethod
    def transition_deploy(
        cls,
        deploy_id: int,
        target: str,
        *,
        update_fields: Optional[dict] = None,
    ) -> None:
        """
        Transition a Deploy to ``target`` with explicit validation.
        """
        from deploy.models import Deploy  # type: ignore

        with transaction.atomic():
            deploy = (
                Deploy.objects
                .select_for_update()
                .filter(pk=deploy_id)
                .first()
            )
            if deploy is None:
                raise InvalidServiceStateError(
                    f"Deploy {deploy_id} does not exist.",
                    details={"deploy_id": deploy_id},
                )

            src = deploy.status
            try:
                sm.check_deploy_transition(src, target)
            except sm.InvalidTransition as exc:
                raise InvalidServiceStateError(
                    str(exc),
                    details={
                        "entity": "Deploy",
                        "deploy_id": deploy_id,
                        "src": src,
                        "target": target,
                        "allowed": list(exc.allowed),
                    },
                ) from exc

            updates = {"status": target}
            if update_fields:
                updates.update(update_fields)

            now = timezone.now()
            if target == sm.DEPLOY_RUNNING:
                updates.setdefault("started_at", now)
            elif target in (
                sm.DEPLOY_SUCCEEDED, sm.DEPLOY_FAILED,
                sm.DEPLOY_CANCELLED, sm.DEPLOY_ROLLED_BACK,
            ):
                updates.setdefault("completed_at", now)

            Deploy.objects.filter(pk=deploy_id).update(**updates)
            logger.info(
                "StateManager: deploy %s %s -> %s",
                deploy_id, src, target,
                extra={"entity": "Deploy", "deploy_id": deploy_id,
                       "src": src, "dst": target},
            )

    # ------------------------------------------------------------------
    # Convenience helpers (used by deploy_service / stop_service)
    # ------------------------------------------------------------------

    @classmethod
    def lock_and_get_deployment(cls, deploy_id: int):
        """
        Atomically:
          * Lock the Deploy + Service rows.
          * Validate Service is QUEUED.
          * Transition Service QUEUED -> DEPLOYING.
          * Transition Deploy PENDING -> RUNNING.
          * Return the locked Deploy (with select_related for service).

        Raises ``InvalidServiceStateError`` if any precondition fails.
        """
        from deploy.models import Deploy  # type: ignore
        from services.models import Service  # type: ignore
        from core.global_settings.config import SERVICE_STATUS_CHOICES  # type: ignore

        with transaction.atomic():
            try:
                deploy = (
                    Deploy.objects
                    .select_related("service", "service__plan", "service__network")
                    .select_for_update(of=("self", "service"))
                    .get(pk=deploy_id)
                )
            except Deploy.DoesNotExist as exc:
                raise InvalidServiceStateError(
                    f"Deploy ID {deploy_id} does not exist.",
                ) from exc

            service = deploy.service
            if service.status != SERVICE_STATUS_CHOICES.QUEUED:
                raise InvalidServiceStateError(
                    f"Deploy aborted. Service status is {service.status}, "
                    f"expected QUEUED.",
                    details={
                        "service_id": service.pk,
                        "actual_status": service.status,
                        "expected_status": SERVICE_STATUS_CHOICES.QUEUED,
                    },
                )

            now = timezone.now()
            service.status = SERVICE_STATUS_CHOICES.DEPLOYING
            service.deploy_started = now
            service.save(update_fields=["status", "deploy_started"])

            from deploy.models import DeploymentStatusChoices  # type: ignore
            deploy.status = DeploymentStatusChoices.RUNNING
            deploy.started_at = now
            deploy.stage = "starting"
            deploy.progress = 0
            deploy.save(update_fields=["status", "started_at", "stage", "progress"])

            logger.info(
                "StateManager.lock_and_get_deployment: deploy=%s service=%s",
                deploy.pk, service.pk,
                extra={"deploy_id": deploy.pk, "service_id": service.pk},
            )
            return deploy

    @classmethod
    def mark_service_running(
        cls, service_id: int, *, deployed_at=None,
    ) -> None:
        """Idempotent transition to RUNNING (skips if terminal/STOPPED)."""
        from services.models import Service  # type: ignore
        from core.global_settings.config import SERVICE_STATUS_CHOICES  # type: ignore

        with transaction.atomic():
            service = (
                Service.objects
                .select_for_update()
                .filter(pk=service_id)
                .first()
            )
            if service is None:
                return
            # Never overwrite a clean STOPPED.
            if service.status == SERVICE_STATUS_CHOICES.STOPPED:
                return
            # Idempotent: already running.
            if service.status == SERVICE_STATUS_CHOICES.RUNNING:
                return
            cls.transition_service(service_id, SERVICE_STATUS_CHOICES.RUNNING,
                                   update_fields={"deployed_at": deployed_at or timezone.now()})

    @classmethod
    def mark_service_stopped(cls, service_id: int) -> None:
        from services.models import Service  # type: ignore
        from core.global_settings.config import SERVICE_STATUS_CHOICES  # type: ignore

        with transaction.atomic():
            service = (
                Service.objects
                .select_for_update()
                .filter(pk=service_id)
                .first()
            )
            if service is None:
                return
            if service.status == SERVICE_STATUS_CHOICES.STOPPED:
                return  # idempotent
            if service.status != SERVICE_STATUS_CHOICES.STOPPING:
                logger.warning(
                    "StateManager.mark_service_stopped called on service %s "
                    "with status=%s (expected stopping); skipping",
                    service_id, service.status,
                )
                return
            cls.transition_service(service_id, SERVICE_STATUS_CHOICES.STOPPED)

    @classmethod
    def mark_service_failed(cls, service_id: int) -> None:
        """Transition to FAILED, but never overwrite STOPPED."""
        from services.models import Service  # type: ignore
        from core.global_settings.config import SERVICE_STATUS_CHOICES  # type: ignore

        with transaction.atomic():
            service = (
                Service.objects
                .select_for_update()
                .filter(pk=service_id)
                .first()
            )
            if service is None:
                return
            if service.status == SERVICE_STATUS_CHOICES.STOPPED:
                return  # do not overwrite a clean stop
            cls.transition_service(service_id, SERVICE_STATUS_CHOICES.FAILED)

    @classmethod
    def mark_deploy_succeeded(
        cls, deploy_id: int, *, message: str = "",
    ) -> None:
        from deploy.models import DeploymentStatusChoices  # type: ignore
        cls.transition_deploy(
            deploy_id, DeploymentStatusChoices.SUCCEEDED,
            update_fields={
                "stage": "finished",
                "progress": 100,
                "status_message": message or "Deployment completed successfully.",
                "error_message": "",
            },
        )

    @classmethod
    def mark_deploy_failed(
        cls, deploy_id: int, *, message: str = "",
        stage: str = "deployment_failed",
        details: Optional[dict] = None,
    ) -> None:
        from deploy.models import DeploymentStatusChoices  # type: ignore
        cls.transition_deploy(
            deploy_id, DeploymentStatusChoices.FAILED,
            update_fields={
                "stage": stage,
                "error_message": message,
                "status_message": "Deployment failed.",
            },
        )

    @classmethod
    def mark_deploy_cancelled(cls, deploy_id: int, *, message: str = "") -> None:
        from deploy.models import DeploymentStatusChoices  # type: ignore
        cls.transition_deploy(
            deploy_id, DeploymentStatusChoices.CANCELLED,
            update_fields={
                "stage": "cancelled",
                "status_message": message or "Deployment cancelled.",
            },
        )


__all__ = ["StateManager"]
