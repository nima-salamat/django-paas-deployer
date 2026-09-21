from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class DeploymentActivationConsistencyContractTests(unittest.TestCase):
    """Dependency-free regression contracts for the deployment lifecycle.

    These tests intentionally validate the source-level safety boundaries that
    can be checked without Django/Docker. Runtime integration tests belong in
    the normal project environment where those services are available.
    """

    def setUp(self):
        self.orchestrator = (ROOT / "deployments/core/orchestrator.py").read_text()
        self.container = (ROOT / "deployments/core/manager/container_manager.py").read_text()
        self.service = (ROOT / "deployments/celery/services/deploy_service.py").read_text()
        self.scheduler = (ROOT / "deployments/celery/schedules.py").read_text()
        self.api = (ROOT / "deploy/apis.py").read_text()

    def test_new_deploy_is_not_marked_selected_when_queued(self):
        queue_section = self.api.split("def cancel(", 1)[0]
        self.assertNotIn('"selected_deploy": deploy', queue_section)

    def test_activation_is_after_readiness(self):
        readiness = self.orchestrator.index("health = self.health_checker.wait_until_healthy")
        activation = self.orchestrator.index("self._activation_callback()")
        self.assertLess(readiness, activation)

    def test_activation_requires_previous_selection_to_match(self):
        self.assertIn("if current != previous_deploy_id:", self.service)

    def test_each_replacement_router_has_deployment_identity(self):
        self.assertIn('router_name=f"{config.name}-deploy-', self.orchestrator)
        self.assertIn('"deployment.id": str(config.labels.get("deployment.id")', self.orchestrator)

    def test_router_priority_and_readiness_healthcheck_are_explicit(self):
        self.assertIn("traefik.http.routers.{self.router_name}.priority", self.container)
        self.assertIn("traefik.http.services.{self.router_name}.loadbalancer.healthcheck.path", self.container)

    def test_stale_recovery_requires_positive_resource_ownership(self):
        self.assertIn("owned_by_deploy", self.scheduler)
        self.assertIn('str(labels.get("deployment.id") or "") == str(locked.pk)', self.scheduler)

    def test_stale_recovery_only_inferrs_success_at_activation(self):
        self.assertIn('stage == "activation"', self.scheduler)
        self.assertIn("Deployment worker stopped responding before activation", self.scheduler)

    def test_stale_worker_does_not_get_to_infer_success_from_old_container(self):
        self.assertIn("healthy", self.scheduler)
        self.assertIn("ambiguous crashes", self.scheduler)


if __name__ == "__main__":
    unittest.main()
