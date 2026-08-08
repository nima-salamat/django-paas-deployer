"""
deployments/celery/service_status.py
------------------------------------
Backward-compatible facade over the new ``StateManager``.

The original ``ServiceStateManager`` had several unsafe methods:
  * ``sync_legacy_failure`` could overwrite a clean STOPPED with FAILED.
  * ``sync_legacy_stopped`` could overwrite a RUNNING with STOPPED.
  * ``sync_legacy_success`` could overwrite a FAILED with RUNNING.
  * ``lock_and_start_stopping`` did NOT validate source state.

All of these now delegate to the explicit ``StateManager`` which
validates transitions via ``deployments.common.state_machine``.  The
public method signatures are preserved so existing call sites
(``DeployService``, ``StopService``, monitor actions, schedules) keep
working without code changes.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from deploy.models import Deploy, DeploymentStatusChoices  # type: ignore
from services.models import Service  # type: ignore
from core.global_settings.config import SERVICE_STATUS_CHOICES  # type: ignore

from deployments.core.state.manager import StateManager
from deployments.core.state.locks import acquire_service_deployment_lock
from deployments.common.exceptions import InvalidServiceStateError

logger = logging.getLogger(__name__)


class ServiceStateManager:
    """
    Thin facade over ``StateManager``.

    All mutating methods delegate to ``StateManager`` so transitions are
    validated against the state machine.  Methods that previously did
    bare ``.update()`` (the ``sync_legacy_*`` family) now use
    ``StateManager.transition_*`` which raises ``InvalidServiceStateError``
    on illegal transitions.  Callers that want the old "ignore invalid
    transitions" behaviour can catch the exception.
    """

    # ------------------------------------------------------------------
    # Locking + initial state setup
    # ------------------------------------------------------------------

    @classmethod
    def lock_and_get_deployment(cls, deploy_id: int) -> Deploy:
        return StateManager.lock_and_get_deployment(deploy_id)

    @classmethod
    @transaction.atomic
    def lock_and_start_stopping(cls, service_id: int) -> Service:
        """
        Transition Service -> STOPPING with source-state validation.

        Accepts RUNNING, FAILED, SUCCEEDED (legacy alias), and STOPPING
        (idempotent).  Rejects QUEUED, DEPLOYING, STOPPED.
        """
        try:
            service = (
                Service.objects
                .select_for_update()
                .get(pk=service_id)
            )
        except Service.DoesNotExist as exc:
            raise InvalidServiceStateError(
                f"Service ID {service_id} does not exist."
            ) from exc

        allowed = (
            SERVICE_STATUS_CHOICES.RUNNING,
            SERVICE_STATUS_CHOICES.FAILED,
            SERVICE_STATUS_CHOICES.SUCCEEDED,  # legacy alias
            SERVICE_STATUS_CHOICES.STOPPING,   # idempotent
        )
        if service.status not in allowed:
            raise InvalidServiceStateError(
                f"Cannot stop service in status={service.status}. "
                f"Allowed: {[s for s in allowed]}.",
                details={
                    "service_id": service_id,
                    "actual": service.status,
                    "allowed": list(allowed),
                },
            )

        if service.status == SERVICE_STATUS_CHOICES.STOPPING:
            return service  # idempotent

        service.status = SERVICE_STATUS_CHOICES.STOPPING
        service.save(update_fields=["status"])
        logger.info(
            "ServiceStateManager: service %s %s -> stopping",
            service_id, service.status,
        )
        return service

    # ------------------------------------------------------------------
    # sync_legacy_* — now SAFE (validate before update)
    # ------------------------------------------------------------------

    @classmethod
    def sync_legacy_success(
        cls,
        service_id: int,
        deploy_id: int | None = None,
    ) -> None:
        """
        Mark deploy SUCCEEDED and service RUNNING.

        Validates: service must not be STOPPED (operator's stop wins).
        If the service is in any other non-terminal state, transition
        to RUNNING; otherwise log and skip.
        """
        try:
            StateManager.mark_service_running(service_id)
        except InvalidServiceStateError as exc:
            logger.warning(
                "sync_legacy_success: refusing to overwrite service %s state: %s",
                service_id, exc,
            )
            return

        if deploy_id is not None:
            try:
                StateManager.mark_deploy_succeeded(
                    deploy_id, message="Deployment completed successfully.",
                )
            except InvalidServiceStateError as exc:
                logger.warning(
                    "sync_legacy_success: refusing to overwrite deploy %s state: %s",
                    deploy_id, exc,
                )

    @classmethod
    def sync_legacy_failure(
        cls,
        service_id: int,
        deploy_id: int | None = None,
    ) -> None:
        """
        Mark deploy FAILED and service FAILED.

        NEVER overwrites a clean STOPPED — the operator's stop wins.
        """
        try:
            StateManager.mark_service_failed(service_id)
        except InvalidServiceStateError as exc:
            logger.warning(
                "sync_legacy_failure: refusing to overwrite service %s state: %s",
                service_id, exc,
            )
            return

        if deploy_id is not None:
            try:
                StateManager.mark_deploy_failed(
                    deploy_id, message="Deployment failed.",
                )
            except InvalidServiceStateError as exc:
                logger.warning(
                    "sync_legacy_failure: refusing to overwrite deploy %s state: %s",
                    deploy_id, exc,
                )

    @classmethod
    def sync_legacy_stopped(cls, service_id: int) -> None:
        """
        Mark service STOPPED.  Validates: must be STOPPING.
        """
        try:
            StateManager.mark_service_stopped(service_id)
        except InvalidServiceStateError as exc:
            logger.warning(
                "sync_legacy_stopped: refusing to overwrite service %s state: %s",
                service_id, exc,
            )

    # ------------------------------------------------------------------
    # Monitor-facing writers (kept for backward compat)
    # ------------------------------------------------------------------

    @classmethod
    def mark_running(cls, service_id: int, *, deployed_at=None) -> None:
        StateManager.mark_service_running(service_id, deployed_at=deployed_at)

    @classmethod
    def mark_stopped(cls, service_id: int) -> None:
        StateManager.mark_service_stopped(service_id)

    @classmethod
    def mark_failed(cls, service_id: int) -> None:
        StateManager.mark_service_failed(service_id)


__all__ = [
    "ServiceStateManager",
    "acquire_service_deployment_lock",
]
