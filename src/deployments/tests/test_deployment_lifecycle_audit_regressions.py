"""Regression coverage for the deployment lifecycle audit fixes."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from deployments.application import DeploymentExecutionContext, DeploymentLifecycleExecutor, InMemoryLifecycleStore
from deployments.core.state.locks import DeploymentLock
from deployments.reconciliation import (
    DesiredRuntimeState,
    ReconciliationAction,
    ReconciliationDecision,
    ReconciliationExecutionContext,
    ReconciliationExecutor,
)
from deployments.runtime import RuntimeIdentity, RuntimeRegistry
from deployments.runtime.fake import FakeRuntime
from deployments.runtime.errors import RuntimeOperationError
from deployments.common.exceptions import StaleDeploymentWorkerError
from deployments.common import state_machine as sm


ROOT = Path(__file__).resolve().parents[2]


def test_advisory_lock_key_is_stable_for_uuid_and_integer_forms():
    import uuid

    service_uuid = uuid.UUID("acb08cf5-fc73-4f6f-918f-6d5df31b3aa1")
    assert DeploymentLock(service_uuid)._key() == DeploymentLock(str(service_uuid))._key()
    assert DeploymentLock(123)._key() == DeploymentLock("123")._key()
    assert DeploymentLock(123)._key() != DeploymentLock(uuid.UUID(int=123))._key()


@pytest.mark.deployment_integration
@pytest.mark.django_db(transaction=True)
def test_postgres_advisory_lock_is_shared_across_uuid_forms_and_sessions():
    import uuid

    import psycopg2
    from django.db import connection, transaction
    from deployments.common.exceptions import DeploymentLockError

    from deployments.core.state.locks import (
        acquire_service_deployment_lock,
        acquire_service_deployment_transaction_lock,
    )

    service_uuid = uuid.uuid4()
    string_key = DeploymentLock(str(service_uuid))._key()
    connect_args = connection.get_connection_params()
    with acquire_service_deployment_lock(service_uuid) as lock:
        assert lock.assert_held()
        with psycopg2.connect(**connect_args) as second_session:
            with second_session.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [string_key])
                acquired_while_owned = cursor.fetchone()[0]
        assert acquired_while_owned is False

    with psycopg2.connect(**connect_args) as second_session:
        with second_session.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [string_key])
            acquired_after_release = cursor.fetchone()[0]
            if acquired_after_release:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [string_key])
    assert acquired_after_release is True

    with psycopg2.connect(**connect_args) as deployment_session:
        with deployment_session.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [string_key])
            try:
                with transaction.atomic():
                    with pytest.raises(DeploymentLockError):
                        with acquire_service_deployment_transaction_lock(service_uuid):
                            pytest.fail("deletion must not pass an active worker lock")
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [string_key])

    with transaction.atomic():
        with acquire_service_deployment_transaction_lock(service_uuid):
            pass


def test_reconciliation_rejects_a_changed_active_revision():
    context = ReconciliationExecutionContext(
        service_id="service-1",
        lifecycle_generation=7,
        active_revision_id="revision-old",
        owns_execution=lambda: True,
        current_generation=lambda: 7,
        current_active_revision=lambda: "revision-new",
    )

    with pytest.raises(StaleDeploymentWorkerError, match="stale active revision"):
        context.assert_current()


def test_reconciliation_journals_resources_before_apply_and_after_readiness():
    runtime = FakeRuntime()
    events = []
    original_apply = runtime.apply
    original_wait_ready = runtime.wait_ready

    def apply(plan, *, operation_key, cancel_check=None):
        events.append("runtime.apply")
        return original_apply(plan, operation_key=operation_key, cancel_check=cancel_check)

    def wait_ready(handle, *, timeout=None, cancel_check=None):
        events.append("runtime.wait_ready")
        return original_wait_ready(handle, timeout=timeout, cancel_check=cancel_check)

    runtime.apply = apply
    runtime.wait_ready = wait_ready
    identity = RuntimeIdentity(
        service_id="service-1",
        deployment_id="deploy-1",
        revision_id="revision-1",
        runtime_name="app-service-1",
    )
    plan = SimpleNamespace(
        identity=identity,
        required_capabilities=frozenset(),
        runtime_options={"processes": [{"name": "web", "enabled": True}]},
    )
    selection = RuntimeRegistry({"swarm": runtime}).resolve(
        policy={"backend": "swarm"}, probe=True
    )
    journal_states = []
    context = ReconciliationExecutionContext(
        service_id="service-1",
        lifecycle_generation=2,
        active_revision_id="revision-1",
        owns_execution=lambda: True,
        current_generation=lambda: 2,
        current_active_revision=lambda: "revision-1",
        journal_runtime_resources=lambda *, state, **_kwargs: journal_states.append(state),
    )
    desired = DesiredRuntimeState(
        service_id="service-1",
        revision_id="revision-1",
        desired_state="running",
        runtime_name="app-service-1",
    )
    decision = ReconciliationDecision(
        action=ReconciliationAction.CREATE,
        reason_code="missing",
        message="Create missing runtime.",
        service_id="service-1",
        runtime_name="app-service-1",
    )

    result = ReconciliationExecutor().execute(
        decision,
        desired=desired,
        selection=selection,
        runtime=runtime,
        context=context,
        plan=plan,
    )

    assert result.success is True
    assert journal_states == ["planned", "created", "ready", "active"]
    assert events == ["runtime.apply", "runtime.wait_ready"]


def test_partial_reconciliation_recovery_rechecks_generation_before_cleanup():
    generation = {"value": 4}
    runtime = FakeRuntime()
    recovery_side_effects = []

    def fail_apply(*_args, **_kwargs):
        raise RuntimeOperationError(
            "partial Swarm apply failed",
            code="runtime_apply_failed",
        )

    def recover(_details, *, operation_key, cancel_check=None):
        generation["value"] = 5
        if cancel_check is not None:
            cancel_check()
        recovery_side_effects.append(operation_key)
        return {}

    runtime.apply = fail_apply
    runtime.recover_failed_apply = recover
    selection = RuntimeRegistry({"swarm": runtime}).resolve(
        policy={"backend": "swarm"}, probe=True
    )
    identity = RuntimeIdentity(
        service_id="service-1",
        deployment_id="deploy-1",
        revision_id="revision-1",
        runtime_name="app-service-1",
    )
    plan = SimpleNamespace(
        identity=identity,
        required_capabilities=frozenset(),
        runtime_options={"processes": [{"name": "web", "enabled": True}]},
    )
    context = ReconciliationExecutionContext(
        service_id="service-1",
        lifecycle_generation=4,
        active_revision_id="revision-1",
        owns_execution=lambda: True,
        current_generation=lambda: generation["value"],
        current_active_revision=lambda: "revision-1",
    )
    desired = DesiredRuntimeState(
        service_id="service-1",
        revision_id="revision-1",
        desired_state="running",
        runtime_name="app-service-1",
    )
    decision = ReconciliationDecision(
        action=ReconciliationAction.CREATE,
        reason_code="missing",
        message="Create missing runtime.",
        service_id="service-1",
        runtime_name="app-service-1",
    )

    with pytest.raises(RuntimeOperationError) as error:
        ReconciliationExecutor().execute(
            decision,
            desired=desired,
            selection=selection,
            runtime=runtime,
            context=context,
            plan=plan,
        )

    assert recovery_side_effects == []
    assert "stale lifecycle generation" in error.value.details["recovery_error"]


def test_deployment_executor_journals_planned_resources_before_runtime_apply():
    runtime = FakeRuntime()
    events = []
    original_apply = runtime.apply

    def apply(plan, *, operation_key, cancel_check=None):
        events.append("runtime.apply")
        return original_apply(plan, operation_key=operation_key, cancel_check=cancel_check)

    runtime.apply = apply
    identity = RuntimeIdentity(
        service_id="service-1",
        deployment_id="deploy-1",
        revision_id="revision-1",
        runtime_name="app-service-1",
    )
    selection = RuntimeRegistry({"swarm": runtime}).resolve(
        policy={"backend": "swarm"}, probe=True
    )
    context = DeploymentExecutionContext(
        deployment_id="deploy-1",
        service_id="service-1",
        revision_id="revision-1",
        worker_task_id="worker-1",
        operation_key="deploy-1:attempt-1",
        runtime_selection=selection,
    )

    class JournalStore(InMemoryLifecycleStore):
        def journal_runtime_resource(self, _context, *, state, **_kwargs):
            events.append(f"journal.{state}")

    plan = SimpleNamespace(
        identity=identity,
        required_capabilities=frozenset(),
        runtime_options={"processes": [{"name": "web", "enabled": True}]},
    )
    strategy = SimpleNamespace(
        plan=lambda _context: plan,
        activate=lambda *_args: None,
    )

    result = DeploymentLifecycleExecutor(JournalStore()).execute(context, strategy, runtime)

    assert result.success is True
    assert events[0] == "journal.planned"
    assert events.index("journal.planned") < events.index("runtime.apply")
    assert events[-1] == "journal.active"


@pytest.mark.django_db
def test_database_resource_journal_records_cancel_cleanup_and_checks_generation():
    from types import SimpleNamespace

    from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices
    from deploy.models import Deploy, DeploymentResource
    from deployments.infrastructure.django_lifecycle import DjangoDeploymentLifecycleStore
    from plans.models import Plan
    from services.models import PrivateNetwork, Service
    from users.models import User

    user = User.objects.create_user(
        username="lifecycle-journal-test",
        email="lifecycle-journal-test@example.invalid",
    )
    plan = Plan.objects.create(
        name=NameChoices.BRONZE,
        platform="docker",
        plan_type=PlanTypeChoices.APP,
        max_cpu=1,
        max_ram=512,
        max_storage=10,
        price_per_hour=0,
        storage_type=StorageTypeChoices.SSD,
    )
    network = PrivateNetwork.objects.create(name="journal-test-network", user=user)
    service = Service.objects.create(
        name="journal-test", user=user, plan=plan, network=network
    )
    service.lifecycle_generation = 8
    service.task_id = "worker-1"
    service.save(update_fields=["lifecycle_generation", "task_id", "updated_at"])
    deploy = Deploy.objects.create(
        name="journal-test-deploy",
        service=service,
        version=1.0,
        status="running",
        execution_task_id="worker-1",
        cancel_requested=True,
        expected_lifecycle_generation=8,
    )
    context = SimpleNamespace(
        expected_lifecycle_generation=8,
        worker_task_id="worker-1",
        assert_can_continue=lambda: None,
    )
    store = DjangoDeploymentLifecycleStore(deploy.pk, task_id="worker-1")

    store.journal_runtime_resource(
        context,
        kind="runtime_service",
        name="app-journal-test",
        state="retired",
        error="cancelled during readiness",
    )
    resource = DeploymentResource.objects.get(deployment=deploy)
    assert resource.state == "retired"
    assert resource.retired_at is not None
    assert resource.last_error == "cancelled during readiness"

    Service.objects.filter(pk=service.pk).update(lifecycle_generation=9)
    with pytest.raises(StaleDeploymentWorkerError, match="lifecycle generation changed"):
        store.journal_runtime_resource(
            context,
            kind="runtime_service",
            name="app-journal-test",
            state="cleanup_pending",
            error="stale worker must not overwrite journal state",
        )


@pytest.mark.django_db
def test_activation_replaces_expected_active_revision_and_rejects_stale_replacement():
    from core.global_settings.config import NameChoices, PlanTypeChoices, StorageTypeChoices
    from deploy.models import Deploy
    from deployments.core.state.manager import ActivationOutcome, StateManager
    from plans.models import Plan
    from services.models import PrivateNetwork, Service, ServiceRevision
    from users.models import User

    user = User.objects.create_user(
        username="activation-cas-test",
        email="activation-cas-test@example.invalid",
    )
    plan = Plan.objects.create(
        name=NameChoices.BRONZE,
        platform="docker",
        plan_type=PlanTypeChoices.APP,
        max_cpu=1,
        max_ram=512,
        max_storage=10,
        price_per_hour=0,
        storage_type=StorageTypeChoices.SSD,
    )
    network = PrivateNetwork.objects.create(name="activation-cas-network", user=user)
    service = Service.objects.create(
        name="activation-cas-service", user=user, plan=plan, network=network
    )
    previous_deploy = Deploy.objects.create(
        name="activation-cas-v1",
        service=service,
        version=1.0,
        status="succeeded",
    )
    previous_revision = ServiceRevision.objects.create(
        service=service,
        revision_number=1,
        state=ServiceRevision.State.ACTIVE,
        source_deploy=previous_deploy,
    )
    Deploy.objects.filter(pk=previous_deploy.pk).update(revision=previous_revision)
    Service.objects.filter(pk=service.pk).update(
        active_revision=previous_revision,
        selected_deploy=previous_deploy,
        status="running",
        desired_state="running",
        lifecycle_generation=10,
        task_id="worker-v2",
    )

    replacement = Deploy.objects.create(
        name="activation-cas-v2",
        service=service,
        version=2.0,
        status="running",
        execution_task_id="worker-v2",
        previous_deploy=previous_deploy,
        expected_lifecycle_generation=10,
        expected_active_revision_id=str(previous_revision.pk),
    )
    replacement_revision = ServiceRevision.objects.create(
        service=service,
        revision_number=2,
        source_deploy=replacement,
    )
    Deploy.objects.filter(pk=replacement.pk).update(revision=replacement_revision)

    outcome = {}
    assert StateManager.activate_revision_and_succeed(
        replacement.pk,
        replacement_revision.pk,
        task_id="worker-v2",
        expected_lifecycle_generation=10,
        expected_previous_deploy_id=str(previous_deploy.pk),
        enforce_previous_deploy=True,
        expected_active_revision_id=str(previous_revision.pk),
        allow_active_revision_replacement=True,
        outcome=outcome,
    )
    service.refresh_from_db()
    previous_revision.refresh_from_db()
    replacement.refresh_from_db()
    assert str(service.active_revision_id) == str(replacement_revision.pk)
    assert previous_revision.state == ServiceRevision.State.SUPERSEDED
    assert replacement.status == "succeeded"
    assert outcome["value"] == ActivationOutcome.ACTIVATED

    stale = Deploy.objects.create(
        name="activation-cas-stale",
        service=service,
        version=3.0,
        status="running",
        execution_task_id="worker-v3",
        expected_lifecycle_generation=10,
        expected_active_revision_id=str(previous_revision.pk),
    )
    stale_revision = ServiceRevision.objects.create(
        service=service,
        revision_number=3,
        source_deploy=stale,
    )
    Deploy.objects.filter(pk=stale.pk).update(revision=stale_revision)
    Service.objects.filter(pk=service.pk).update(task_id="worker-v3")
    outcome = {}
    assert not StateManager.activate_revision_and_succeed(
        stale.pk,
        stale_revision.pk,
        task_id="worker-v3",
        expected_lifecycle_generation=10,
        expected_active_revision_id=str(previous_revision.pk),
        allow_active_revision_replacement=True,
        outcome=outcome,
    )
    service.refresh_from_db()
    assert str(service.active_revision_id) == str(replacement_revision.pk)
    assert outcome["value"] == ActivationOutcome.ACTIVATION_CONFLICT


def test_active_resource_journal_failure_keeps_committed_deployment_successful():
    runtime = FakeRuntime()
    identity = RuntimeIdentity(
        service_id="service-1",
        deployment_id="deploy-journal-failure",
        revision_id="revision-1",
        runtime_name="app-service-1",
    )
    selection = RuntimeRegistry({"swarm": runtime}).resolve(
        policy={"backend": "swarm"}, probe=True
    )
    context = DeploymentExecutionContext(
        deployment_id="deploy-journal-failure",
        service_id="service-1",
        revision_id="revision-1",
        worker_task_id="worker-1",
        operation_key="deploy-journal-failure:attempt-1",
        runtime_selection=selection,
    )

    class JournalFailureStore(InMemoryLifecycleStore):
        finalization = None

        def journal_runtime_resource(self, _context, *, state, **_kwargs):
            if state == "active":
                raise RuntimeError("journal database unavailable")

        def record_finalization(self, _context, details):
            self.finalization = dict(details)

    plan = SimpleNamespace(
        identity=identity,
        required_capabilities=frozenset(),
        runtime_options={"processes": [{"name": "web", "enabled": True}]},
    )
    strategy = SimpleNamespace(plan=lambda _context: plan, activate=lambda *_args: None)
    store = JournalFailureStore()

    result = DeploymentLifecycleExecutor(store).execute(context, strategy, runtime)

    assert result.success is True
    assert result.status == sm.DEPLOY_SUCCEEDED
    assert result.details["journal_update_failed"] is True
    assert result.details["reconciliation_required"] is True
    assert store.finalization["journal_update_failed"] is True


def test_cancellation_at_activation_boundary_is_terminalized():
    runtime = FakeRuntime()
    selection = RuntimeRegistry({"swarm": runtime}).resolve(
        policy={"backend": "swarm"}, probe=True
    )
    cancel_state = {"requested": False}
    context = DeploymentExecutionContext(
        deployment_id="deploy-cancel-race",
        service_id="service-1",
        revision_id="revision-1",
        worker_task_id="worker-1",
        operation_key="deploy-cancel-race:attempt-1",
        runtime_selection=selection,
        owns_execution=lambda: True,
        cancellation_requested=lambda: cancel_state["requested"],
    )
    plan = SimpleNamespace(
        identity=RuntimeIdentity(
            service_id="service-1",
            deployment_id="deploy-cancel-race",
            revision_id="revision-1",
            runtime_name="app-service-1",
        ),
        required_capabilities=frozenset(),
        runtime_options={"processes": [{"name": "web", "enabled": True}]},
    )
    strategy = SimpleNamespace(
        plan=lambda _context: plan,
        activate=lambda *_args: None,
    )

    class CancellationRaceStore(InMemoryLifecycleStore):
        def transition(self, current_context, target, **kwargs):
            if target == sm.DEPLOY_SUCCEEDED:
                cancel_state["requested"] = True
                self.last_activation_outcome = "cancelled"
                return False
            return super().transition(current_context, target, **kwargs)

    store = CancellationRaceStore()
    result = DeploymentLifecycleExecutor(store).execute(context, strategy, runtime)

    assert result.success is False
    assert result.status == sm.DEPLOY_CANCELLED
    assert store.status == sm.DEPLOY_CANCELLED


def _run_automatic_rollback(*, restored_revision_ready):
    runtime = FakeRuntime()
    selection = RuntimeRegistry({"swarm": runtime}).resolve(
        policy={"backend": "swarm"}, probe=True
    )
    old_identity = RuntimeIdentity(
        service_id="service-1",
        deployment_id="deploy-old",
        revision_id="revision-old",
        runtime_name="app-service-1",
    )
    new_identity = RuntimeIdentity(
        service_id="service-1",
        deployment_id="deploy-new",
        revision_id="revision-new",
        runtime_name="app-service-1",
    )
    old_plan = SimpleNamespace(
        identity=old_identity,
        required_capabilities=frozenset(),
        runtime_options={},
    )
    old_handle = runtime.apply(old_plan, operation_key="old/apply").handle
    runtime.wait_ready(old_handle)
    new_plan = SimpleNamespace(
        identity=new_identity,
        required_capabilities=frozenset(),
        runtime_options={},
        rollback_plan=old_plan,
    )
    new_handle = runtime.apply(new_plan, operation_key="new/apply").handle
    context = DeploymentExecutionContext(
        deployment_id="deploy-new",
        service_id="service-1",
        revision_id="revision-new",
        worker_task_id="worker-1",
        operation_key="deploy-new:attempt-1",
        runtime_selection=selection,
        owns_execution=lambda: True,
        cancellation_requested=lambda: False,
    )
    if not restored_revision_ready:
        runtime.set_readiness_error(
            old_identity,
            RuntimeOperationError(
                "The previous revision failed readiness.",
                code="runtime_readiness_failed",
            ),
        )
    return DeploymentLifecycleExecutor._recover_failure(
        context,
        runtime,
        new_plan,
        new_handle,
        readiness_timeout=1,
    )


def test_automatic_rollback_is_complete_only_after_previous_revision_is_ready():
    rollback_performed, rollback_failed, details = _run_automatic_rollback(
        restored_revision_ready=True
    )

    assert rollback_performed is True
    assert rollback_failed is False
    assert details["rollback_ready"] is True


def test_automatic_rollback_readiness_failure_is_not_projected_as_running():
    rollback_performed, rollback_failed, details = _run_automatic_rollback(
        restored_revision_ready=False
    )

    assert rollback_performed is False
    assert rollback_failed is True
    assert "rollback_error" in details


def test_activation_and_force_cancel_paths_are_fenced_and_non_destructive():
    manager = (ROOT / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    native = (ROOT / "deployments/infrastructure/django_lifecycle.py").read_text(encoding="utf-8")
    runtime_api = (ROOT / "services/api/runtime.py").read_text(encoding="utf-8")
    force_cancel = runtime_api.split("def force_cancel_deploy_apiview", 1)[1].split(
        "def service_status_apiview", 1
    )[0]
    settings = (ROOT / "config/settings.py").read_text(encoding="utf-8")

    activation = manager.split("def activate_revision_and_succeed", 1)[1].split(
        "def transition_deploy_system_terminal", 1
    )[0]
    assert "expected_active_revision_id" in activation
    assert "allow_active_revision_replacement" in activation
    assert "ActivationOutcome.CANCELLED" in activation
    assert "allow_active_revision_replacement=self.allow_active_revision_replacement" in native
    assert "CELERY_TASK_REJECT_ON_WORKER_LOST = True" in settings
    assert "terminate=False" in force_cancel
    assert "project_service=False" in force_cancel
    assert "force_cancel_deploy_cleanup.apply_async(" in force_cancel
    assert "_force_cancel_runtime_cleanup(" not in force_cancel


def test_force_cancel_cleanup_rechecks_generation_before_runtime_and_projection():
    runtime = (ROOT / "services/api/runtime.py").read_text(encoding="utf-8")
    tasks = (ROOT / "deployments/celery/tasks.py").read_text(encoding="utf-8")
    cleanup = runtime.split("def _force_cancel_runtime_cleanup", 1)[1].split(
        "def force_cancel_deploy_apiview", 1
    )[0]
    task = tasks.split("def force_cancel_deploy_cleanup", 1)[1].split(
        "def _finalize_owned_deployment_failure", 1
    )[0]

    assert "ownership_check=None" in cleanup
    assert cleanup.index("assert_owner()") < cleanup.index("runtime.remove(name)")
    assert "ownership_check=owns_cleanup" in task
    assert "Service.objects.select_for_update()" in task
    assert '"lifecycle_generation"' in task
    assert "StaleDeploymentWorkerError" in task


def test_stale_worker_recovery_retires_journaled_resources_already_absent_from_swarm():
    schedules = (ROOT / "deployments/celery/schedules.py").read_text(encoding="utf-8")
    recovery = schedules.split(
        "def _recover_stale_swarm_worker_without_ready_runtime", 1
    )[1].split("def _recover_stale_running_deploys_swarm", 1)[0]

    assert "except DockerNotFound" in recovery
    assert 'resource.state = "retired"' in recovery
    assert "resource.retired_at = timezone.now()" in recovery
    assert "Runtime ownership labels do not match the lost deployment." in recovery
    assert 'resource.state = "cleanup_pending"' in recovery


def test_direct_service_deletion_uses_lifecycle_lock_and_owned_cleanup():
    signals = (ROOT / "services/signals.py").read_text(encoding="utf-8")
    admin = (ROOT / "services/api/admin_services.py").read_text(encoding="utf-8")
    user = (ROOT / "services/api/user_services.py").read_text(encoding="utf-8")
    delete_signal = signals.split(
        "@receiver(pre_delete, sender=Service)", 1
    )[1].split("def _cleanup_service_volumes", 1)[0]
    admin_destroy = admin.split("def destroy(self, request, *args, **kwargs):", 1)[1].split(
        "class AdminPrivateNetworkViewSet", 1
    )[0]
    user_destroy = user.split("def destroy(self, request, pk=None", 1)[1].split(
        "def retrieve(", 1
    )[0]

    assert "acquire_service_deployment_transaction_lock(instance.pk)" in delete_signal
    assert 'bump_lifecycle(instance.pk, desired_state="deleted")' in delete_signal
    assert "cleanup_service_resources(instance)" in delete_signal
    assert "_purge_service_runtime(service)" not in admin_destroy
    assert "except DeploymentLockError" in admin_destroy
    assert "except DeploymentLockError" in user_destroy


def test_admin_start_persists_running_intent_and_revision_snapshot():
    admin = (ROOT / "services/api/admin_services.py").read_text(encoding="utf-8")
    start = admin.split("def admin_start_service_apiview", 1)[1].split(
        "def admin_stop_service_apiview", 1
    )[0]

    assert 'bump_lifecycle(service_item.pk, desired_state="running")' in start
    assert '"desired_state": "running"' in start
    assert "expected_lifecycle_generation=generation" in start
    assert "expected_active_revision_id=str(service_item.active_revision_id" in start


def test_release_selection_cannot_change_runtime_authority_without_rollout():
    api = (ROOT / "deploy/apis.py").read_text(encoding="utf-8")
    selection = api.split("def set_deploy_apiview", 1)[1].split("def unset_deploy_apiview", 1)[0]
    unselection = api.split("def unset_deploy_apiview", 1)[1].split(
        "# ------------------------------------------------------------------\n# Credential generation", 1
    )[0]

    assert "runtime_activation_required" in selection
    assert "activate_revision_locked(" not in selection
    assert "A release can only become active through deployment or rollback." in selection
    assert "active_revision_id=None" not in unselection
    assert "cannot be unselected without a runtime stop or rollback" in unselection


def test_database_deployment_holds_service_lock_before_claiming_rows():
    tasks = (ROOT / "deployments/celery/tasks.py").read_text(encoding="utf-8")
    task = tasks.split("def run_db_deploy(", 1)[1].split(
        "def _run_db_deploy_locked(", 1
    )[0]

    assert task.index("acquire_service_deployment_lock(service_id)") < task.index(
        "_run_db_deploy_locked(self, deploy_id, force_reinit)"
    )
    locked_body = tasks.split("def _run_db_deploy_locked(", 1)[1]
    assert "_lock_for_db_deploy(" in locked_body


def test_successful_automatic_rollback_restores_service_projection_with_cas():
    service = (ROOT / "deployments/celery/services/deploy_service.py").read_text(
        encoding="utf-8"
    )
    state_manager = (ROOT / "deployments/core/state/manager.py").read_text(
        encoding="utf-8"
    )

    assert "rollback_restored_active_revision = bool(" in service
    assert 'failure_details.get("rollback_ready")' in service
    assert "expected_active_revision_id=str(" in service
    assert 'expected_desired_state="running"' in service
    transition = state_manager.split("def transition_service(", 1)[1].split(
        "def _project_service_after_cancellation(", 1
    )[0]
    assert "expected_active_revision_id" in transition
    assert "expected_desired_state" in transition


def test_deployment_intent_migration_backfills_and_retains_outbox_events():
    migration = (ROOT / "deploy/migrations/0033_deployment_intent_and_outbox_retention.py").read_text()

    assert "backfill_deployment_intent" in migration
    assert "expected_lifecycle_generation" in migration
    assert "expected_active_revision_id" in migration
    assert "worker_recovery_attempts" in migration
    assert "on_delete=django.db.models.deletion.SET_NULL" in migration



def test_deployment_intent_schema_repair_is_idempotent_and_backfills_missing_values():
    migration = (
        ROOT
        / "deploy/migrations/0035_repair_missing_deploy_intent_columns.py"
    ).read_text(encoding="utf-8")

    assert "get_table_description" in migration
    assert "schema_editor.add_field" in migration
    assert "expected_lifecycle_generation" in migration
    assert "expected_active_revision_id" in migration
    assert "worker_recovery_attempts" in migration
    assert "bulk_update" in migration


def test_developer_shell_consumer_imports_posixpath_for_relative_cd():
    consumer = (ROOT / "services/consumers.py").read_text(encoding="utf-8")

    assert "import posixpath" in consumer
    assert "posixpath.join(self.session.workdir, target)" in consumer
    assert "posixpath.normpath(candidate)" in consumer
