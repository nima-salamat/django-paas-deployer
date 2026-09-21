from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class IntegratedLifecycleContractTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_catalog_install_snapshots_definition_and_private_network(self):
        models = self.read("app_catalog/models.py")
        services = self.read("app_catalog/services.py")
        self.assertIn("definition_snapshot = models.JSONField", models)
        self.assertIn("network = models.OneToOneField", models)
        self.assertIn("definition_snapshot=copy.deepcopy(definition.data)", services)
        self.assertIn("network=network", services)

    def test_duplicate_application_start_does_not_reassign_owner(self):
        executor = self.read("app_catalog/executor.py")
        self.assertIn('if instance.status == ApplicationStatus.DEPLOYING:', executor)
        self.assertIn('current_owner and requested_owner and current_owner != requested_owner', executor)

    def test_catalog_labels_reach_container(self):
        deploy_service = self.read("deployments/celery/services/deploy_service.py")
        self.assertIn('**dict(cfg.get("labels") or {})', deploy_service)
        container = self.read("deployments/core/orchestrator.py")
        self.assertIn('"application.id"', self.read("app_catalog/services.py"))
        self.assertIn('"managed-by": "django-paas-deployer"', container)

    def test_global_docker_prune_is_not_performed_by_deployment_cleanup(self):
        cleanup = self.read("deployments/core/cleanup.py")
        self.assertIn("host-wide Docker GC is operator-managed", cleanup)
        self.assertNotIn("Image.prune_dangling_images()", cleanup)

    def test_stale_name_conflict_cleanup_checks_ownership(self):
        container = self.read("deployments/core/manager/container_manager.py")
        self.assertIn("ownership mismatch", container)
        self.assertIn('labels.get("managed-by")', container)

    def test_manual_active_selection_requires_success(self):
        api = self.read("deploy/apis.py")
        self.assertIn('deploy_item.status != DeploymentStatusChoices.SUCCEEDED', api)
        self.assertIn('"deploy_not_ready"', api)

    def test_catalog_duplicate_ids_are_rejected(self):
        catalog = self.read("app_catalog/catalog.py")
        self.assertIn("Duplicate catalog id", catalog)


    def test_optional_service_cancel_does_not_fail_application(self):
        executor = self.read("app_catalog/executor.py")
        self.assertIn('plan_required.get(b.service_key, True)\n            and b.deploy.status == DeploymentStatusChoices.CANCELLED', executor)

    def test_application_delete_requires_terminal_state(self):
        api = self.read("app_catalog/apis.py")
        self.assertIn('application_not_terminal', api)
        self.assertIn('application_children_active', api)

    def test_selected_activation_still_occurs_after_readiness(self):
        orchestrator = self.read("deployments/core/orchestrator.py")
        ready_marker = 'health = self.health_checker.wait_until_healthy('
        activation = 'if self._activation_callback is not None:'
        self.assertLess(orchestrator.index(ready_marker), orchestrator.index(activation))


if __name__ == "__main__":
    unittest.main()


def test_catalog_gate_uses_installed_plan_snapshot_not_live_catalog():
    text = Path("app_catalog/tasks.py").read_text()
    assert "ApplicationStackExecutor(instance_id)._load()" in text
    assert "ApplicationCatalog.get(instance.catalog_id)" not in text

def test_internal_catalog_services_do_not_join_public_proxy_network_without_port():
    text = Path("deployments/core/deploy.py").read_text()
    assert "and self.port" in text
    assert 'NetworkSpec(name="proxy_net"' in text



def test_application_reconciliation_recovers_lost_start_and_cancel_tasks():
    text = Path("app_catalog/tasks.py").read_text()
    assert "status=ApplicationStatus.PENDING" in text
    assert "start_application_installation.delay" in text
    assert "ApplicationStackExecutor(str(instance.pk)).cancel" in text

def test_application_queue_failure_does_not_leave_permanent_pending_state():
    text = Path("app_catalog/apis.py").read_text()
    assert "APPLICATION_TASK_QUEUE_FAILED" in text
    assert "HTTP_503_SERVICE_UNAVAILABLE" in text
