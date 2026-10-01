"""Django persistence adapter for deployment cancellation."""

from __future__ import annotations

import uuid

from django.db import transaction

from deploy.models import Deploy
from deployments.application.cancel import DeploymentCancellationResult
from deployments.application.cancellation import (
    CancellationAction,
    DeploymentCancellationSnapshot,
    decide_cancellation,
)
from deployments.core.state.manager import StateManager


class DjangoDeploymentCancellationGateway:
    """Apply the pure cancellation policy under the authoritative row lock."""

    def cancel(self, deploy_id: int) -> DeploymentCancellationResult:
        with transaction.atomic():
            locked = (
                Deploy.objects
                .select_for_update()
                .get(pk=deploy_id)
            )
            decision = decide_cancellation(
                DeploymentCancellationSnapshot(
                    status=locked.status,
                    cancel_requested=locked.cancel_requested,
                )
            )
            if decision.action is CancellationAction.CANCEL_PENDING:
                Deploy.objects.filter(pk=locked.pk).update(cancel_requested=True)
                StateManager.transition_deploy_system_terminal(
                    locked.pk,
                    decision.target_status,
                    update_fields={
                        "cancel_requested": True,
                        "stage": decision.stage,
                        "progress": decision.progress,
                        "status_message": decision.status_message,
                        "error_message": "",
                    },
                    event_payload={
                        "event_id": str(uuid.uuid4()),
                        "trace_id": str(locked.pk),
                        "deployment_id": str(locked.pk),
                        "service_id": str(locked.service_id),
                        "revision_id": str(getattr(locked, "revision_id", "") or ""),
                        "task_id": "cancellation-gateway",
                        "event_type": "deployment.cancelled.warning",
                        "stage": str(decision.stage or "cancelled"),
                        "level": "warning",
                        "message": decision.status_message or "Deployment cancelled.",
                        "progress": decision.progress,
                        "details": {"controlled_by": "cancellation_gateway"},
                    },
                )
            else:
                updates = {"cancel_requested": True}
                if decision.stage is not None:
                    updates["stage"] = decision.stage
                if decision.status_message is not None:
                    updates["status_message"] = decision.status_message
                Deploy.objects.filter(pk=locked.pk).update(**updates)

            return DeploymentCancellationResult(
                decision=decision,
                execution_task_id=locked.execution_task_id or "",
            )


__all__ = ["DjangoDeploymentCancellationGateway"]
