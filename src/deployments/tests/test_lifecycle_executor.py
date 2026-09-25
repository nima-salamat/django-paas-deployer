"""Pure lifecycle tests for ownership, cancellation, retry and rollback."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from deployments.application import (
    DeploymentExecutionContext,
    DeploymentLifecycleExecutor,
    InMemoryLifecycleStore,
)
from deployments.common import state_machine as sm
from deployments.runtime import RuntimeIdentity, RuntimeRegistry
from deployments.runtime.errors import RuntimeOperationError
from deployments.runtime.fake import FakeRuntime


def _context(identity, *, owns=lambda: True, cancelled=lambda: False, events=None):
    runtime_selection = RuntimeRegistry({"swarm": FakeRuntime()}).resolve(
        policy={"backend": "swarm"}
    )
    return DeploymentExecutionContext(
        deployment_id=identity.deployment_id or "deployment-1",
        service_id=identity.service_id,
        revision_id=identity.revision_id,
        worker_task_id="worker-1",
        operation_key="deployment-1/attempt-1",
        runtime_selection=runtime_selection,
        owns_execution=owns,
        cancellation_requested=cancelled,
        publish=(events.append if events is not None else lambda event: None),
    )


class _Strategy:
    def __init__(self, plan, *, activate=None, error=None):
        self.plan_value = plan
        self.activate_callback = activate
        self.error = error
        self.activated = 0

    def plan(self, context):
        if self.error:
            raise self.error
        return self.plan_value

    def activate(self, context, plan, readiness):
        self.activated += 1
        if self.activate_callback:
            self.activate_callback()


def _plan(identity, **values):
    return SimpleNamespace(identity=identity, required_capabilities=frozenset(), **values)


def test_lifecycle_executor_runs_pending_running_succeeded():
    runtime = FakeRuntime()
    identity = RuntimeIdentity(
        service_id="service-1",
        deployment_id="deployment-1",
        revision_id="revision-1",
        runtime_name="app-service-1",
    )
    events = []
    strategy = _Strategy(_plan(identity))
    store = InMemoryLifecycleStore()

    result = DeploymentLifecycleExecutor(store).execute(
        _context(identity, events=events), strategy, runtime
    )

    assert result.success is True
    assert result.status == sm.DEPLOY_SUCCEEDED
    assert store.history == [
        (sm.DEPLOY_PENDING, sm.DEPLOY_RUNNING),
        (sm.DEPLOY_RUNNING, sm.DEPLOY_SUCCEEDED),
    ]
    assert strategy.activated == 1
    assert [event.stage for event in events] == [
        "planning", "runtime_apply", "readiness", "deployment_completed"
    ]


def test_lifecycle_executor_classifies_retryable_runtime_failure():
    runtime = FakeRuntime()
    identity = RuntimeIdentity(service_id="service-1", runtime_name="app-service-1")
    runtime.set_readiness_error(
        identity,
        RuntimeOperationError(
            "temporary runtime failure",
            code="runtime_temporary_failure",
            recoverable=True,
        ),
    )
    store = InMemoryLifecycleStore()

    result = DeploymentLifecycleExecutor(store).execute(
        _context(identity), _Strategy(_plan(identity)), runtime
    )

    assert result.success is False
    assert result.status == sm.DEPLOY_FAILED
    assert result.retryable is True
    assert result.error.code == "runtime_temporary_failure"


def test_lifecycle_executor_cancels_before_runtime_side_effects():
    runtime = FakeRuntime()
    identity = RuntimeIdentity(service_id="service-1", runtime_name="app-service-1")
    store = InMemoryLifecycleStore()

    result = DeploymentLifecycleExecutor(store).execute(
        _context(identity, cancelled=lambda: True), _Strategy(_plan(identity)), runtime
    )

    assert result.status == sm.DEPLOY_CANCELLED
    assert result.success is False
    assert runtime.apply_count == 0


def test_stale_worker_cannot_cleanup_or_transition_new_owner_state():
    runtime = FakeRuntime()
    identity = RuntimeIdentity(service_id="service-1", runtime_name="app-service-1")
    owner = {"current": True}
    strategy = _Strategy(_plan(identity))

    def lose_owner():
        owner["current"] = False

    strategy.activate_callback = lose_owner
    store = InMemoryLifecycleStore()
    result = DeploymentLifecycleExecutor(store).execute(
        _context(identity, owns=lambda: owner["current"]), strategy, runtime
    )

    assert result.status == "stale"
    assert store.status == sm.DEPLOY_RUNNING
    assert store.history == [(sm.DEPLOY_PENDING, sm.DEPLOY_RUNNING)]
    assert runtime.remove_count == 0


def test_cancellation_wins_completion_race_and_cleans_owned_runtime():
    runtime = FakeRuntime()
    identity = RuntimeIdentity(service_id="service-1", runtime_name="app-service-1")
    requested = {"value": False}
    strategy = _Strategy(_plan(identity), activate=lambda: requested.__setitem__("value", True))
    store = InMemoryLifecycleStore()

    result = DeploymentLifecycleExecutor(store).execute(
        _context(identity, cancelled=lambda: requested["value"]), strategy, runtime
    )

    assert result.success is False
    assert result.status == sm.DEPLOY_CANCELLED
    assert runtime.remove_count == 1


def test_invalid_terminal_transition_remains_rejected():
    store = InMemoryLifecycleStore(status=sm.DEPLOY_SUCCEEDED)
    identity = RuntimeIdentity(service_id="service-1", runtime_name="app-service-1")
    context = _context(identity)

    assert store.ensure_running(context) is False
    assert store.status == sm.DEPLOY_SUCCEEDED


def test_known_unavailable_runtime_is_blocked_before_planning():
    runtime = FakeRuntime(reachable=False)
    identity = RuntimeIdentity(service_id="service-1", runtime_name="app-service-1")
    selection = RuntimeRegistry({"swarm": runtime}).resolve(
        policy={"backend": "swarm"}, probe=True
    )
    context = DeploymentExecutionContext(
        deployment_id="deployment-1",
        service_id=identity.service_id,
        revision_id=identity.revision_id,
        worker_task_id="worker-1",
        operation_key="deployment-1/attempt-1",
        runtime_selection=selection,
    )
    strategy = _Strategy(_plan(identity))

    result = DeploymentLifecycleExecutor(InMemoryLifecycleStore()).execute(
        context, strategy, runtime
    )

    assert result.status == sm.DEPLOY_FAILED
    assert result.error.code == "runtime_unreachable"
    assert strategy.activated == 0


def test_unsupported_runtime_capability_is_blocked_before_planning():
    runtime = FakeRuntime(supported=set())
    identity = RuntimeIdentity(service_id="service-1", runtime_name="app-service-1")
    selection = RuntimeRegistry({"swarm": runtime}).resolve(
        policy={"backend": "swarm"},
        required_capabilities={"service_scheduling"},
    )
    context = _context(identity)
    context = replace(context, runtime_selection=selection)

    result = DeploymentLifecycleExecutor(InMemoryLifecycleStore()).execute(
        context, _Strategy(_plan(identity)), runtime
    )

    assert result.status == sm.DEPLOY_FAILED
    assert result.error.code == "runtime_capability_unsupported"
