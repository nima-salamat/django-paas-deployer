"""Pure cancellation policy for deployment executions.

This module deliberately knows nothing about Django, Celery, or HTTP.  It
decides what cancellation means for a snapshot of deployment state; a
persistence adapter applies that decision while holding the authoritative row
lock.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from deployments.common.state_machine import (
    DEPLOY_CANCELLED,
    DEPLOY_PENDING,
    DEPLOY_ROLLING_BACK,
    DEPLOY_RUNNING,
)


class CancellationAction(str, Enum):
    """State-changing action selected by the cancellation policy."""

    CANCEL_PENDING = "cancel_pending"
    REQUEST_STOP = "request_stop"
    MARK_REQUESTED = "mark_requested"


@dataclass(frozen=True)
class DeploymentCancellationSnapshot:
    """Minimal state needed to make a cancellation decision."""

    status: str
    cancel_requested: bool = False


@dataclass(frozen=True)
class DeploymentCancellationDecision:
    """Deterministic cancellation decision for one locked snapshot."""

    action: CancellationAction
    previous_status: str
    target_status: str | None = None
    stage: str | None = None
    progress: int | None = None
    status_message: str | None = None


def decide_cancellation(
    snapshot: DeploymentCancellationSnapshot,
) -> DeploymentCancellationDecision:
    """Return the safe cancellation action for ``snapshot``.

    Pending work can be made terminal immediately.  Work that is already
    executing, including rollback, must first receive a cancellation token so
    its owner can stop Docker/build work and clean up safely.  Terminal and
    otherwise non-running states retain the historical idempotent behavior of
    recording the request without inventing a new transition.
    """

    if snapshot.status == DEPLOY_PENDING:
        return DeploymentCancellationDecision(
            action=CancellationAction.CANCEL_PENDING,
            previous_status=snapshot.status,
            target_status=DEPLOY_CANCELLED,
            stage="cancelled",
            progress=100,
            status_message="Deployment cancelled by user.",
        )

    if snapshot.status in {DEPLOY_RUNNING, DEPLOY_ROLLING_BACK}:
        return DeploymentCancellationDecision(
            action=CancellationAction.REQUEST_STOP,
            previous_status=snapshot.status,
            stage="cancel_requested",
            status_message="Cancellation requested; stopping deployment work.",
        )

    return DeploymentCancellationDecision(
        action=CancellationAction.MARK_REQUESTED,
        previous_status=snapshot.status,
    )


__all__ = [
    "CancellationAction",
    "DeploymentCancellationDecision",
    "DeploymentCancellationSnapshot",
    "decide_cancellation",
]
