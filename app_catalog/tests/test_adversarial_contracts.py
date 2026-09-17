from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_catalog_task_gate_uses_celery_task_ownership_token():
    text = (ROOT / "app_catalog" / "tasks.py").read_text("utf-8")
    assert "binding.dispatch_task_id != str(self.request.id)" in text
    assert "task_id=child_task_id" in text
    assert "advance_application_service.si(instance_id, service_key, child_task_id)" in text


def test_application_terminal_reconciliation_locks_row():
    text = (ROOT / "app_catalog" / "executor.py").read_text("utf-8")
    assert "ApplicationInstance.objects.select_for_update().get(pk=self.instance_id)" in text
    assert "locked.cancel_requested" in text


def test_ownership_labels_cannot_be_overridden_by_catalog_labels():
    text = (ROOT / "deployments" / "core" / "orchestrator.py").read_text("utf-8")
    assert 'if str(k) not in {"managed-by", "deployment.id", "service.id"}' in text
    assert '"managed-by": "django-paas-deployer"' in text


def test_application_cancel_and_delete_ordering_is_explicit():
    text = (Path(__file__).resolve().parents[1] / "apis.py").read_text("utf-8")
    assert "ApplicationInstance.objects.select_for_update().get(pk=instance.pk)" in text
    assert "for row in service_rows:" in text
    assert "row.service.delete()" in text
    assert "network.delete()" in text


def test_stale_name_conflict_cleanup_requires_deployment_identity():
    text = (ROOT / "deployments" / "core" / "manager" / "container_manager.py").read_text("utf-8")
    assert "if expected_deploy:" in text
    assert "owns_resource = False" in text


def test_database_services_do_not_join_proxy_network_by_default():
    text = (ROOT / "deployments" / "celery" / "tasks.py").read_text("utf-8")
    assert 'public_db = bool(cfg.get("public") or cfg.get("public_host") or cfg.get("expose_public"))' in text
    assert 'if public_db:' in text


def test_compose_external_build_context_is_rejected_instead_of_dropped():
    text = (ROOT / "app_catalog" / "compose_catalog.py").read_text("utf-8")
    assert "uses an external build context" in text
    assert '"dockerfile": _transform(str(inline_dockerfile)' in text


def test_application_binding_model_matches_migration_and_runtime_usage():
    model = (ROOT / "app_catalog" / "models.py").read_text("utf-8")
    migration = (ROOT / "app_catalog" / "migrations" / "0001_initial.py").read_text("utf-8")
    assert 'deploy = models.OneToOneField' in model
    assert 'name="deploy"' in migration or '"deploy.deploy"' in migration


def test_private_network_delete_requires_docker_ownership_label():
    text = (ROOT / "services" / "signals.py").read_text("utf-8")
    assert 'labels.get("managed-by") != "django-paas-deployer"' in text
    assert 'Refusing to remove Docker network' in text

def test_service_delete_requires_owned_container_labels():
    source = Path('services/signals.py').read_text()
    assert 'Refusing to remove container' in source
    assert 'labels.get("service.id") == expected_service' in source
    assert 'owns_selected_deploy' in source

def test_container_create_does_not_silently_drop_restart_or_tmpfs_semantics():
    source = Path('deployments/core/manager/container_manager.py').read_text()
    assert 'without restart_policy' not in source
    assert 'without tmpfs' not in source
    assert 'Runtime semantics such as restart policy, tmpfs' in source

def test_network_create_rechecks_ownership_after_name_conflict():
    source = Path('deployments/core/manager/network_manager.py').read_text()
    assert 'network = self.client.networks.get(self.name)' in source
    assert 'exists but is not owned by PassDeployer' in source

def test_volume_reuse_and_cleanup_require_managed_ownership():
    manager = Path('deployments/core/manager/volume_manager.py').read_text()
    signals = Path('services/signals.py').read_text()
    assert 'exists but is not owned by PassDeployer' in manager
    assert 'labels.get("managed-by") != "django-paas-deployer"' in signals

def test_service_state_machine_allows_runtime_failure_after_activation():
    source = Path('deployments/common/state_machine.py').read_text()
    assert '(SERVICE_RUNNING, SERVICE_FAILED)' in source
    assert '(SERVICE_SUCCEEDED, SERVICE_FAILED)' in source

def test_deployment_state_finish_uses_owned_terminal_transition():
    source = Path('deploy/deployment_state.py').read_text()
    assert 'transition_deploy_terminal_if_owned' in source
    assert 'Ignoring stale/duplicate terminal result' in source

def test_deploy_service_syncs_service_only_from_committed_terminal_state():
    source = Path('deployments/celery/services/deploy_service.py').read_text()
    assert 'final_status = final.get("status")' in source
    assert 'final_status == "succeeded"' in source
    assert 'selected_id' in source

def test_terminal_state_manager_rechecks_cancel_under_lock():
    source = Path('deployments/core/state/manager.py').read_text()
    assert 'if target != sm.DEPLOY_CANCELLED and deploy.cancel_requested:' in source
    assert 'target = sm.DEPLOY_CANCELLED' in source
