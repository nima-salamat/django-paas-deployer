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


def test_registry_uses_operator_managed_cluster_scope_and_enabled_state():
    runtime = FakeRuntime()
    selection = RuntimeRegistry({"swarm": runtime}).resolve(
        cluster=SimpleNamespace(name="primary", enabled=False),
        probe=False,
    )

    assert selection.cluster == "primary"
    assert selection.availability.operator_enabled is False
    assert selection.can_execute is False


def test_registry_reads_swarm_enabled_only_as_compatibility_input(monkeypatch):
    monkeypatch.setenv("SWARM_ENABLED", "0")
    selection = RuntimeRegistry({}).resolve(probe=False)

    assert selection.backend == "legacy_docker"
    assert selection.availability.state == RuntimeAvailabilityState.UNSUPPORTED
    assert selection.reason == "legacy SWARM_ENABLED compatibility input"


def test_registry_does_not_allow_deployment_or_revision_to_select_backend(monkeypatch):
    monkeypatch.delenv("DEPLOYMENT_RUNTIME_BACKEND", raising=False)
    monkeypatch.delenv("SWARM_ENABLED", raising=False)
    runtime = FakeRuntime()

    selection = RuntimeRegistry({"swarm": runtime}).resolve(
        service={"backend": "legacy_docker"},
        revision={"runtime_backend": "legacy_docker"},
        deployment={"backend": "legacy_docker"},
    )

    assert selection.backend == "swarm"
    assert selection.reason == "default backend: swarm"


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

    def wait_ready(self, name, *, timeout, expected_image=None, cancel_check=None):
        return self.state

    def stop(self, name):
        return None

    def remove(self, name):
        return None

    def service_logs(self, name, *, tail):
        return b"ready\n"


def test_swarm_adapter_apply_does_not_reference_out_of_scope_primary_contract():
    runtime = _StubSwarmRuntime()
    adapter = SwarmRuntimeAdapter(runtime=runtime, operator_enabled=True)
    identity = RuntimeIdentity(
        service_id="service-1",
        deployment_id="deployment-1",
        revision_id="revision-1",
        runtime_name="app-service-1",
    )
    contract = SimpleNamespace(
        as_dict=lambda: {
            "entrypoint_source": "IMAGE",
            "image_entrypoint": ["docker-ensure-installed.sh"],
            "image_cmd": ["app", "serve"],
            "command": None,
            "args": ["app", "serve"],
            "catalog_managed": True,
            "image_entrypoint_owned": True,
            "process_name": "web",
            "contract_version": "1",
            "required_executables": [],
            "source_kind": "catalog",
        }
    )
    plan = SimpleNamespace(
        identity=identity,
        deployment_config=SimpleNamespace(image_ref="demo:r1"),
        image_ref="demo:r1",
        execution_contracts={},
        process_graph=SimpleNamespace(
            processes=(
                SimpleNamespace(
                    name="web",
                    command="app serve",
                    entrypoint=None,
                ),
            ),
            runtime={},
            build={},
        ),
        runtime_options={"execution_contract": contract.as_dict()},
        environment={},
        resources={},
        networks=(),
        volumes=(),
        endpoints=(),
        labels={},
        release_id=None,
        health_policy={},
    )

    result = adapter.apply(plan, operation_key="deployment-1/apply")

    assert result.success is True
    assert result.handle.metadata["execution_contract"]["entrypoint_source"] == "IMAGE"


def test_swarm_adapter_preserves_expected_image_and_startup_timeout_for_readiness():
    class RecordingRuntime(_StubSwarmRuntime):
        def __init__(self):
            super().__init__()
            self.wait_ready_calls = []

        def wait_ready(self, name, *, timeout, expected_image=None):
            self.wait_ready_calls.append(
                {
                    "name": name,
                    "timeout": timeout,
                    "expected_image": expected_image,
                }
            )
            return self.state

    runtime = RecordingRuntime()
    adapter = SwarmRuntimeAdapter(runtime=runtime, operator_enabled=True)
    identity = RuntimeIdentity(
        service_id="service-1",
        deployment_id="deployment-1",
        revision_id="revision-1",
        runtime_name="app-service-1",
    )
    plan = SimpleNamespace(
        identity=identity,
        deployment_config=SimpleNamespace(
            image_ref="demo:r1",
            start_timeout=45,
            health_timeout=60,
        ),
        image_ref="demo:r1",
    )

    result = adapter.apply(plan, operation_key="deployment-1/apply")
    adapter.wait_ready(result.handle, timeout=5)

    assert result.handle.metadata["expected_image"] == "demo:r1"
    assert runtime.wait_ready_calls[-1]["expected_image"] == "demo:r1"
    assert runtime.wait_ready_calls[-1]["timeout"] == pytest.approx(5)


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


def test_swarm_inspection_does_not_treat_an_unlabelled_external_service_as_current_revision():
    runtime = _StubSwarmRuntime()
    runtime.state = SwarmServiceState(
        name=runtime.state.name,
        service_id=runtime.state.service_id,
        replicas_desired=runtime.state.replicas_desired,
        replicas_running=runtime.state.replicas_running,
        tasks=runtime.state.tasks,
    )
    adapter = SwarmRuntimeAdapter(runtime=runtime, operator_enabled=True)
    identity = RuntimeIdentity(
        service_id="service-1",
        deployment_id="deployment-1",
        revision_id="desired-revision",
        runtime_name="app-service-1",
    )

    observed = adapter.inspect(identity)

    assert observed.identity.revision_id is None


def test_swarm_adapter_stop_scales_the_complete_service_group():
    class GroupRuntime(_StubSwarmRuntime):
        def __init__(self):
            super().__init__()
            self.stopped_groups = []

        def stop_service_group(self, service_id):
            self.stopped_groups.append(str(service_id))

    from deployments.runtime.contract import RuntimeHandle

    runtime = GroupRuntime()
    adapter = SwarmRuntimeAdapter(runtime=runtime, operator_enabled=True)
    identity = RuntimeIdentity(
        service_id="service-1",
        deployment_id="deployment-1",
        revision_id="revision-1",
        runtime_name="app-service-1",
    )
    handle = RuntimeHandle(
        backend="swarm",
        identity=identity,
        runtime_id="swarm-service-1",
        resource_name="app-service-1",
    )

    result = adapter.stop(handle, operation_key="service-1/stop")

    assert result.success is True
    assert runtime.stopped_groups == ["service-1"]


def test_swarm_adapter_maps_zero_desired_replicas_to_stopped():
    from dataclasses import replace

    runtime = _StubSwarmRuntime()
    runtime.state = replace(
        runtime.state,
        replicas_desired=0,
        replicas_running=0,
        tasks=(),
    )
    adapter = SwarmRuntimeAdapter(runtime=runtime, operator_enabled=True)
    identity = RuntimeIdentity(
        service_id="service-1",
        runtime_name="app-service-1",
    )

    observation = adapter.inspect(identity)

    assert observation.status.value == "stopped"


def test_service_lifecycle_api_stop_and_start_are_idempotent_and_fenced():
    from pathlib import Path

    src_root = Path(__file__).resolve().parents[2]
    runtime_api = (src_root / "services" / "api" / "runtime.py").read_text(encoding="utf-8")
    start = runtime_api.split("def start_service_apiview", 1)[1].split(
        "def stop_service_apiview", 1
    )[0]
    stop = runtime_api.split("def stop_service_apiview", 1)[1].split(
        "def _force_cancel_runtime_cleanup", 1
    )[0]

    assert start.index("Service is already running.") < start.index(
        "deploy_item = get_active_deploy(service_item)"
    )
    assert "not force_rebuild" in start
    assert '"expected_lifecycle_generation": lifecycle_generation' in stop
    assert "Service stop is already in progress." in stop
    assert "Service is already stopped." in stop


def test_stop_failure_preserves_runtime_truth_and_monitor_supports_replica_sets():
    from pathlib import Path

    src_root = Path(__file__).resolve().parents[2]
    stop_service = (
        src_root / "deployments" / "celery" / "services" / "stop_service.py"
    ).read_text(encoding="utf-8")
    scheduler = (
        src_root / "deployments" / "celery" / "schedules.py"
    ).read_text(encoding="utf-8")
    state_machine = (
        src_root / "deployments" / "common" / "state_machine.py"
    ).read_text(encoding="utf-8")

    assert "sync_legacy_failure" not in stop_service
    assert "DjangoDeploymentState" not in stop_service
    assert "_restore_observed_state_after_failure" in stop_service
    assert "(SERVICE_STOPPING, SERVICE_RUNNING)" in state_machine
    desired_state = scheduler.split("def _reconcile_desired_state", 1)[1].split(
        "def _reconcile_service_runtime", 1
    )[0]
    assert "state.replicas_running == state.replicas_desired" in desired_state
    assert "state.replicas_desired > 0" in desired_state
