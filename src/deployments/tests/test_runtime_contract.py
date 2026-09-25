"""Contract tests for runtime selection and the first fake runtime."""

from types import SimpleNamespace

import pytest

from deployments.core.swarm import SwarmServiceState, SwarmTaskState
from deployments.runtime import (
    RuntimeAvailabilityState,
    RuntimeCapability,
    RuntimeIdentity,
    RuntimeRegistry,
)
from deployments.runtime.errors import RuntimeUnavailableError, RuntimeUnsupportedError
from deployments.runtime.fake import FakeRuntime
from deployments.runtime.swarm import SwarmRuntimeAdapter


def _plan(identity, *, required=()):
    return SimpleNamespace(identity=identity, required_capabilities=frozenset(required))


def test_fake_runtime_apply_wait_and_repeat_are_idempotent():
    runtime = FakeRuntime()
    identity = RuntimeIdentity(
        service_id="service-1",
        deployment_id="deployment-1",
        revision_id="revision-1",
        runtime_name="app-service-1",
    )
    plan = _plan(identity, required={RuntimeCapability.SERVICE_SCHEDULING})

    created = runtime.apply(plan, operation_key="deploy-1/apply")
    repeated = runtime.apply(plan, operation_key="deploy-1/apply")
    ready = runtime.wait_ready(created.handle, timeout=1)

    assert created.changed is True
    assert repeated.idempotent is True
    assert repeated.changed is False
    assert ready.observation.ready is True
    assert runtime.apply_count == 1


def test_fake_runtime_distinguishes_disabled_unavailable_and_unsupported():
    identity = RuntimeIdentity(service_id="service-1", runtime_name="app-service-1")
    plan = _plan(identity, required={RuntimeCapability.PERSISTENT_VOLUMES})

    with pytest.raises(RuntimeUnavailableError) as disabled:
        FakeRuntime(operator_enabled=False).apply(plan, operation_key="disabled")
    assert disabled.value.code == "runtime_disabled"

    with pytest.raises(RuntimeUnavailableError) as unavailable:
        FakeRuntime(reachable=False).apply(plan, operation_key="unavailable")
    assert unavailable.value.code == "runtime_unreachable"

    with pytest.raises(RuntimeUnsupportedError) as unsupported:
        FakeRuntime(supported={RuntimeCapability.SERVICE_SCHEDULING}).apply(
            plan, operation_key="unsupported"
        )
    assert unsupported.value.code == "runtime_capability_unsupported"


def test_fake_runtime_rollback_restores_previous_observation():
    runtime = FakeRuntime()
    identity = RuntimeIdentity(service_id="service-1", runtime_name="app-service-1")
    old_plan = _plan(identity)
    new_plan = _plan(identity)

    first = runtime.apply(old_plan, operation_key="old/apply")
    runtime.wait_ready(first.handle)
    runtime.apply(new_plan, operation_key="new/apply")
    rolled_back = runtime.rollback(new_plan, operation_key="new/rollback")

    assert rolled_back.success is True
    assert rolled_back.observation.ready is True
    assert rolled_back.observation.runtime_id == "fake-app-service-1"


def test_registry_resolves_backend_and_reports_operator_disabled_state():
    runtime = FakeRuntime()
    registry = RuntimeRegistry({"swarm": runtime})

    selection = registry.resolve(
        policy={
            "backend": "swarm",
            "cluster_name": "primary",
            "operator_enabled": False,
        },
        required_capabilities={RuntimeCapability.SERVICE_LOGS},
        probe=True,
    )

    assert selection.backend == "swarm"
    assert selection.cluster == "primary"
    assert selection.reason == "deployment policy"
    assert selection.availability.state == RuntimeAvailabilityState.DISABLED
    assert selection.missing_capabilities == frozenset()
    assert selection.can_execute is False


def test_registry_reads_swarm_enabled_only_as_compatibility_input(monkeypatch):
    monkeypatch.setenv("SWARM_ENABLED", "0")
    selection = RuntimeRegistry({}).resolve(probe=False)

    assert selection.backend == "legacy_docker"
    assert selection.availability.state == RuntimeAvailabilityState.UNSUPPORTED
    assert selection.reason == "legacy SWARM_ENABLED compatibility input"


class _StubSwarmRuntime:
    def __init__(self):
        self.state = SwarmServiceState(
            name="app-service-1",
            service_id="swarm-service-1",
            replicas_desired=1,
            replicas_running=1,
            tasks=(
                SwarmTaskState(
                    task_id="task-1",
                    desired_state="running",
                    state="running",
                    node_id="node-1",
                    node_name="manager-1",
                    error="",
                    message="",
                ),
            ),
            labels={"revision.id": "revision-observed"},
        )

    def assert_active(self):
        return {"LocalNodeState": "active", "ControlAvailable": True}

    def apply(self, config, *, image_ref):
        return self.state

    def inspect_service(self, name):
        return self.state

    def wait_ready(self, name, *, timeout):
        return self.state

    def stop(self, name):
        return None

    def remove(self, name):
        return None

    def service_logs(self, name, *, tail):
        return b"ready\n"


def test_swarm_adapter_translates_existing_runtime_state_without_exposing_sdk_types():
    adapter = SwarmRuntimeAdapter(runtime=_StubSwarmRuntime(), operator_enabled=True)
    identity = RuntimeIdentity(
        service_id="service-1",
        deployment_id="deployment-1",
        revision_id="revision-1",
        runtime_name="app-service-1",
    )
    plan = SimpleNamespace(
        identity=identity,
        deployment_config=SimpleNamespace(image_ref="demo:r1"),
        image_ref="demo:r1",
    )

    result = adapter.apply(plan, operation_key="deployment-1/apply")
    inspected = adapter.inspect(identity)
    ready = adapter.wait_ready(result.handle)

    assert result.success is True
    assert result.observation.ready is True
    assert inspected.runtime_id == "swarm-service-1"
    assert inspected.identity.revision_id == "revision-observed"
    assert ready.observation.tasks[0].task_id == "task-1"
    assert not hasattr(ready.observation, "attrs")
    assert adapter.logs(identity) == b"ready\n"
