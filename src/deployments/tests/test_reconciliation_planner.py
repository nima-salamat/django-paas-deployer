"""Desired/observed reconciliation invariants."""

from deployments.reconciliation import (
    DesiredRuntimeState,
    ReconciliationAction,
    ReconciliationPlanner,
)
from deployments.runtime import RuntimeCapability, RuntimeIdentity, RuntimeRegistry
from deployments.runtime.fake import FakeRuntime
from deployments.runtime.observations import RuntimeObservation, RuntimeObservedStatus


def _selection(runtime=None, **policy):
    runtime = runtime or FakeRuntime()
    return RuntimeRegistry({"swarm": runtime}).resolve(
        policy={"backend": "swarm", **policy},
        probe=True,
    )


def _desired(*, state="running", revision="revision-b"):
    return DesiredRuntimeState(
        service_id="service-1",
        revision_id=revision,
        desired_state=state,
        runtime_name="app-service-1",
        required_capabilities=frozenset({RuntimeCapability.SERVICE_SCHEDULING}),
    )


def _observed(status, *, revision=None):
    return RuntimeObservation(
        identity=RuntimeIdentity(
            service_id="service-1",
            revision_id=revision,
            runtime_name="app-service-1",
        ),
        status=status,
        runtime_id="runtime-1" if status != RuntimeObservedStatus.MISSING else None,
        desired_replicas=1 if status != RuntimeObservedStatus.MISSING else 0,
        ready_replicas=1 if status == RuntimeObservedStatus.READY else 0,
        revision_id=revision,
    )


def test_desired_running_missing_runtime_produces_create():
    decision = ReconciliationPlanner().decide(
        _desired(), _observed(RuntimeObservedStatus.MISSING), _selection()
    )
    assert decision.action == ReconciliationAction.CREATE
    assert decision.reason_code == "runtime_resource_missing"


def test_desired_stopped_running_runtime_produces_stop():
    decision = ReconciliationPlanner().decide(
        _desired(state="stopped", revision=None),
        _observed(RuntimeObservedStatus.READY, revision="revision-a"),
        _selection(),
    )
    assert decision.action == ReconciliationAction.STOP


def test_desired_revision_b_observed_revision_a_produces_update():
    decision = ReconciliationPlanner().decide(
        _desired(revision="revision-b"),
        _observed(RuntimeObservedStatus.READY, revision="revision-a"),
        _selection(),
    )
    assert decision.action == ReconciliationAction.UPDATE
    assert decision.details["desired_revision_id"] == "revision-b"
    assert decision.details["observed_revision_id"] == "revision-a"


def test_repeated_reconciliation_is_deterministic_when_converged():
    planner = ReconciliationPlanner()
    desired = _desired()
    observed = _observed(RuntimeObservedStatus.READY, revision="revision-b")
    first = planner.decide(desired, observed, _selection())
    second = planner.decide(desired, observed, _selection())

    assert first == second
    assert first.action == ReconciliationAction.CONVERGED


def test_runtime_unavailable_blocks_without_destructive_action():
    runtime = FakeRuntime(reachable=False)
    decision = ReconciliationPlanner().decide(
        _desired(), _observed(RuntimeObservedStatus.READY, revision="revision-b"), _selection(runtime)
    )

    assert decision.action == ReconciliationAction.BLOCKED
    assert decision.reason_code == "runtime_unreachable"
    assert decision.recoverable is True


def test_unsupported_capability_is_distinct_from_runtime_unavailable():
    runtime = FakeRuntime(supported={RuntimeCapability.SERVICE_SCHEDULING})
    desired = DesiredRuntimeState(
        service_id="service-1",
        revision_id="revision-b",
        desired_state="running",
        runtime_name="app-service-1",
        required_capabilities=frozenset({RuntimeCapability.PERSISTENT_VOLUMES}),
    )
    decision = ReconciliationPlanner().decide(
        desired, _observed(RuntimeObservedStatus.MISSING), _selection(runtime)
    )

    assert decision.action == ReconciliationAction.BLOCKED
    assert decision.reason_code == "runtime_capability_unsupported"
    assert decision.recoverable is False
