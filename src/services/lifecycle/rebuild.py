"""Safe, fenced runtime teardown for explicit service rebuilds."""

from __future__ import annotations

import logging

from deployments.core.db_deployer import DB_PLATFORMS, DBDeployer
from deployments.core.deploy import Deploy as OrchestratorDeploy
from deployments.core.state.locks import acquire_service_deployment_transaction_lock
from deployments.core.swarm import SwarmRuntime, swarm_enabled
from services.lifecycle.fencing import bump_lifecycle

logger = logging.getLogger(__name__)


def fence_and_teardown_service_runtime(service, *, platform: str) -> tuple[int, str | None]:
    """Fence stale workers, then remove the existing runtime while holding the
    same transaction-scoped advisory lock used by service deletion.

    The caller must already be inside transaction.atomic() and hold the Service
    row lock. The generation bump is committed even when the external teardown
    fails, so a redelivered worker from the previous intent cannot resurrect
    the runtime. Teardown failures are returned rather than raised so callers
    can persist a safe FAILED/STOPPED projection in the same transaction.
    """
    normalized_platform = str(platform or "docker").strip().lower()
    service_id = str(service.pk)
    service_name = service.get_docker_service_name()

    with acquire_service_deployment_transaction_lock(service_id):
        generation = bump_lifecycle(service.pk, desired_state="running")
        try:
            if normalized_platform in DB_PLATFORMS:
                DBDeployer().remove(service_name)
            elif swarm_enabled():
                SwarmRuntime().remove_service_group(service_id)
            else:
                OrchestratorDeploy.remove_all(service_name)
        except Exception as exc:
            logger.exception(
                "Force-rebuild runtime teardown failed for service=%s platform=%s; "
                "the old lifecycle generation has been fenced.",
                service_id,
                normalized_platform,
            )
            return generation, str(exc)[:500]

    return generation, None


def record_force_rebuild_teardown_failure(
    service_id,
    deploy_id,
    *,
    expected_generation: int,
    error: str,
) -> None:
    """Persist a conservative service projection after a failed rebuild teardown."""
    from django.utils import timezone

    from core.global_settings.config import SERVICE_STATUS_CHOICES
    from deploy.models import Deploy
    from deployments.core.state.manager import StateManager
    from services.models import Service

    service = Service.objects.select_for_update().filter(pk=service_id).first()
    if service is None:
        return

    current_status = str(service.status or "").strip().lower()
    target_status = (
        SERVICE_STATUS_CHOICES.STOPPED
        if current_status == str(SERVICE_STATUS_CHOICES.STOPPED).lower()
        else SERVICE_STATUS_CHOICES.FAILED
    )
    StateManager.transition_service(
        service.pk,
        target_status,
        update_fields={
            "desired_state": "stopped",
            "task_id": None,
            "deploy_started": None,
        },
        expected_lifecycle_generation=int(expected_generation),
    )
    Deploy.objects.filter(pk=deploy_id, service_id=service.pk).update(
        reconciliation_required=True,
        cleanup_status="pending",
        cleanup_failures=[
            "Force-rebuild teardown failed: " + str(error or "unknown error")[:500]
        ],
        updated_at=timezone.now(),
    )
