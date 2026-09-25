from deployments.application.cancellation import (
    CancellationAction,
    DeploymentCancellationSnapshot,
    decide_cancellation,
)
from deployments.common.state_machine import (
    DEPLOY_CANCELLED,
    DEPLOY_PENDING,
    DEPLOY_ROLLING_BACK,
    DEPLOY_RUNNING,
    DEPLOY_SUCCEEDED,
)


def test_pending_deployment_is_cancelled_immediately():
    decision = decide_cancellation(
        DeploymentCancellationSnapshot(status=DEPLOY_PENDING)
    )

    assert decision.action is CancellationAction.CANCEL_PENDING
    assert decision.target_status == DEPLOY_CANCELLED
    assert decision.stage == "cancelled"
    assert decision.progress == 100


def test_running_deployment_receives_a_token_for_its_owner():
    for status in (DEPLOY_RUNNING, DEPLOY_ROLLING_BACK):
        decision = decide_cancellation(
            DeploymentCancellationSnapshot(status=status)
        )

        assert decision.action is CancellationAction.REQUEST_STOP
        assert decision.target_status is None
        assert decision.stage == "cancel_requested"


def test_terminal_deployment_cancellation_is_idempotent_request_recording():
    decision = decide_cancellation(
        DeploymentCancellationSnapshot(
            status=DEPLOY_SUCCEEDED,
            cancel_requested=True,
        )
    )

    assert decision.action is CancellationAction.MARK_REQUESTED
    assert decision.target_status is None
