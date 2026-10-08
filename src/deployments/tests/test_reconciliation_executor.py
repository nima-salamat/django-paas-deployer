
from types import SimpleNamespace

import pytest

from deployments.reconciliation import (
    DesiredRuntimeState,
    ReconciliationAction,
    ReconciliationDecision,
    ReconciliationExecutionContext,
    ReconciliationExecutor,
)
from deployments.runtime import RuntimeRegistry, RuntimeIdentity
from deployments.runtime.fake import FakeRuntime
from deployments.runtime.errors import RuntimeOperationError
from deployments.common.exceptions import StaleDeploymentWorkerError


def _selection(runtime):
    return RuntimeRegistry({"swarm": runtime}).resolve(
        policy={"backend": "swarm"},
        probe=True,
    )


def _decision(action):
    return ReconciliationDecision(
        action=action,
        reason_code="test",
        message="test",
        service_id="service-1",
        runtime_name="service-1",
    )


def test_reconciliation_executor_applies_native_plan_with_generation_operation_key():
    runtime = FakeRuntime()
    desired = DesiredRuntimeState(
        service_id="service-1",
        revision_id="revision-2",
        desired_state="running",
        runtime_name="service-1",
    )
    context = ReconciliationExecutionContext(
        service_id="service-1",
        lifecycle_generation=7,
        active_revision_id="revision-2",
        owns_execution=lambda: True,
        current_generation=lambda: 7,
    )
    plan = SimpleNamespace(
        identity=RuntimeIdentity(
            service_id="service-1",
            deployment_id="repair-1",
            revision_id="revision-2",
            runtime_name="service-1",
        ),
        required_capabilities=frozenset(),
        image_ref="demo@sha256:artifact",
    )

    result = ReconciliationExecutor().execute(
        _decision(ReconciliationAction.CREATE),
        desired=desired,
        selection=_selection(runtime),
        runtime=runtime,
        context=context,
        plan=plan,
    )

    assert result is not None
    assert result.success is True
    assert result.handle is not None
    assert runtime.apply_count == 1
    assert any(
        key.startswith("reconcile:service-1:generation:7:revision:revision-2:action:create")
        for key in runtime._operations
    )


def test_reconciliation_executor_recovers_partial_apply_without_handle():
    runtime = FakeRuntime()
    desired = DesiredRuntimeState(
        service_id="service-1",
        revision_id="revision-2",
        desired_state="running",
        runtime_name="service-1",
    )
    context = ReconciliationExecutionContext(
        service_id="service-1",
        lifecycle_generation=7,
        active_revision_id="revision-2",
        owns_execution=lambda: True,
        current_generation=lambda: 7,
    )
    recovered = []

    def failed_apply(plan, *, operation_key, cancel_check=None):
        raise RuntimeOperationError(
            "partial apply",
            code="runtime_apply_failed",
            details={"swarm_recovery": {"remove_services": ["service-1-worker"]}},
        )

    def recover(details, *, operation_key, cancel_check=None):
        recovered.append(details)
        return {"cleanup_attempted": True, "cleanup_failed": False}

    runtime.apply = failed_apply
    runtime.recover_failed_apply = recover

    with pytest.raises(RuntimeOperationError):
        ReconciliationExecutor().execute(
            _decision(ReconciliationAction.CREATE),
            desired=desired,
            selection=_selection(runtime),
            runtime=runtime,
            context=context,
            plan=SimpleNamespace(
                identity=RuntimeIdentity(
                    service_id="service-1",
                    deployment_id="repair-1",
                    revision_id="revision-2",
                    runtime_name="service-1",
                ),
                required_capabilities=frozenset(),
                image_ref="demo@sha256:artifact",
            ),
        )

    assert recovered == [{"swarm_recovery": {"remove_services": ["service-1-worker"]}}]


def test_reconciliation_executor_finalizes_successful_runtime_repair():
    runtime = FakeRuntime()
    desired = DesiredRuntimeState(
        service_id="service-1",
        revision_id="revision-2",
        desired_state="running",
        runtime_name="service-1",
        metadata={"readiness_timeout": 1},
    )
    context = ReconciliationExecutionContext(
        service_id="service-1",
        lifecycle_generation=7,
        active_revision_id="revision-2",
        owns_execution=lambda: True,
        current_generation=lambda: 7,
    )
    called = []

    def finalize(handle, *, operation_key, cancel_check=None):
        called.append((handle.identity.service_id, operation_key))
        return {"cleanup_attempted": True, "cleanup_failed": False}

    runtime.finalize_success = finalize

    result = ReconciliationExecutor().execute(
        _decision(ReconciliationAction.CREATE),
        desired=desired,
        selection=_selection(runtime),
        runtime=runtime,
        context=context,
        plan=SimpleNamespace(
            identity=RuntimeIdentity(
                service_id="service-1",
                deployment_id="repair-1",
                revision_id="revision-2",
                runtime_name="service-1",
            ),
            required_capabilities=frozenset(),
            image_ref="demo@sha256:artifact",
        ),
    )

    assert result is not None and result.success is True
    assert called and called[0][0] == "service-1"


def test_reconciliation_executor_fences_stale_generation_before_mutation():
    runtime = FakeRuntime()
    desired = DesiredRuntimeState(
        service_id="service-1",
        revision_id="revision-2",
        desired_state="running",
        runtime_name="service-1",
    )
    context = ReconciliationExecutionContext(
        service_id="service-1",
        lifecycle_generation=7,
        active_revision_id="revision-2",
        owns_execution=lambda: True,
        current_generation=lambda: 8,
    )

    with pytest.raises(StaleDeploymentWorkerError):
        ReconciliationExecutor().execute(
            _decision(ReconciliationAction.CREATE),
            desired=desired,
            selection=_selection(runtime),
            runtime=runtime,
            context=context,
            plan=SimpleNamespace(image_ref="demo@sha256:artifact"),
        )

    assert runtime.apply_count == 0


def test_reconciliation_executor_requires_handle_for_stop():
    runtime = FakeRuntime()
    desired = DesiredRuntimeState(
        service_id="service-1",
        revision_id=None,
        desired_state="stopped",
        runtime_name="service-1",
    )
    context = ReconciliationExecutionContext(
        service_id="service-1",
        lifecycle_generation=1,
        active_revision_id=None,
        owns_execution=lambda: True,
        current_generation=lambda: 1,
    )

    with pytest.raises(ValueError):
        ReconciliationExecutor().execute(
            _decision(ReconciliationAction.STOP),
            desired=desired,
            selection=_selection(runtime),
            runtime=runtime,
            context=context,
        )


def test_reconciliation_executor_passes_cancellation_to_native_runtime():
    runtime = FakeRuntime()
    desired = DesiredRuntimeState(
        service_id="service-1",
        revision_id="revision-2",
        desired_state="running",
        runtime_name="service-1",
        metadata={"readiness_timeout": 1},
    )
    cancelled = {"value": True}
    context = ReconciliationExecutionContext(
        service_id="service-1",
        lifecycle_generation=3,
        active_revision_id="revision-2",
        owns_execution=lambda: True,
        cancellation_requested=lambda: cancelled["value"],
        current_generation=lambda: 3,
    )
    plan = SimpleNamespace(
        identity=RuntimeIdentity(
            service_id="service-1",
            deployment_id="repair-2",
            revision_id="revision-2",
            runtime_name="service-1",
        ),
        required_capabilities=frozenset(),
        image_ref="demo@sha256:artifact",
    )

    with pytest.raises(RuntimeOperationError) as exc_info:
        ReconciliationExecutor().execute(
            _decision(ReconciliationAction.REPAIR),
            desired=desired,
            selection=_selection(runtime),
            runtime=runtime,
            context=context,
            plan=plan,
        )

    assert getattr(exc_info.value, "code", "") == "runtime_cancelled"
    assert runtime.apply_count == 0
