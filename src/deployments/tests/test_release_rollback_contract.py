from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_rollback_creates_new_immutable_release_with_chronological_parent():
    source = (ROOT / "deploy/apis.py").read_text(encoding="utf-8")
    rollback = source.split("def rollback(", 1)[1].split(
        "def rebuild(", 1
    )[0]

    assert "rollback_release = Release.objects.create(" in rollback
    assert "previous_release=current_release" in rollback
    assert "identity_fingerprint=rollback_release_id" in rollback
    assert "release_reference=rollback_release" in rollback
    assert '"restores_release_id": str(target_release.pk)' in rollback


def test_rollback_activation_is_fenced_and_committed_with_deployment_success():
    state = (ROOT / "deployments/core/state/manager.py").read_text(encoding="utf-8")
    lifecycle = (ROOT / "deployments/infrastructure/django_lifecycle.py").read_text(encoding="utf-8")
    rollback = (ROOT / "deployments/celery/services/rollback_service.py").read_text(encoding="utf-8")

    activation = state.split("def activate_revision_and_succeed", 1)[1].split(
        "def transition_deploy_system_terminal", 1
    )[0]
    assert "expected_active_revision_id" in activation
    assert "allow_active_revision_replacement" in activation
    assert "activate_revision_locked(service, revision_id)" in activation
    assert "allow_active_revision_replacement=self.allow_active_revision_replacement" in lifecycle
    assert "DeploymentLifecycleExecutor(store).execute(" in rollback
    assert "activate_revision_locked(" not in rollback


def test_rollback_recovery_requires_recorded_generation_and_active_revision():
    scheduler = (ROOT / "deployments/celery/schedules.py").read_text(encoding="utf-8")
    requeue = scheduler.split("def _retry_orphaned_queued_deploys", 1)[1].split(
        "def _recover_stale_running_deploys", 1
    )[0]
    stale = scheduler.split("def _recover_stale_running_deploys_swarm", 1)[1].split(
        "def _reconcile_active_deploy", 1
    )[0]

    assert 'getattr(deploy, "operation", "")' in requeue
    assert "expected_lifecycle_generation" in requeue
    assert "rollback_deployment" in requeue
    assert "expected_active_revision_id" in stale
    assert "allow_active_revision_replacement=is_rollback" in stale


def test_rollback_resolves_current_promoted_release_for_revisions_reused_by_rollbacks():
    api = (ROOT / "deploy/apis.py").read_text(encoding="utf-8")
    worker = (ROOT / "deployments/celery/services/rollback_service.py").read_text(encoding="utf-8")

    assert 'revision_id=active_revision_id' in api
    assert 'status="promoted"' in api
    assert 'revision_id=current_deploy.revision_id' in worker
    assert 'status="promoted"' in worker


def test_native_plan_prefers_current_promoted_release_but_accepts_prepared_rollback_target():
    scheduler = (ROOT / "deployments/celery/schedules.py").read_text(encoding="utf-8")
    plan = scheduler.split("def _native_reconciliation_plan", 1)[1].split(
        "def _service_has_active_native_deployment", 1
    )[0]

    promoted_lookup = plan.index('status="promoted"')
    explicit_fallback = plan.index("explicit_release = getattr(deploy, \"release_reference\", None)")
    rollback_check = plan.index('is_rollback_attempt = str(getattr(deploy, "operation", "") or "").lower() == "rollback"')
    assert promoted_lookup < explicit_fallback < rollback_check
    assert 'explicit_status == "promoted"' in plan
    assert '(is_rollback_attempt and explicit_status == "ready")' in plan
    assert "retired historical FK" in plan


def test_service_runtime_reconciliation_repairs_worker_process_drift():
    scheduler = (ROOT / "deployments/celery/schedules.py").read_text(encoding="utf-8")
    reconcile = scheduler.split("def _reconcile_service_runtime_swarm", 1)[1].split(
        "def _native_reconciliation_plan", 1
    )[0]

    assert "_swarm_process_group_health(" in reconcile
    assert "RuntimeObservedStatus.DEGRADED" in reconcile
    assert "ReconciliationPlanner().decide(desired, observed, selection)" in reconcile
