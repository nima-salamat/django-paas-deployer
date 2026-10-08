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

    def test_activation_is_idempotent_for_the_same_revision(self):
        self.assertIn("if str(service.active_revision_id or \"\") == str(deploy_item.revision_id):", self.service)
        self.assertIn("Activation already committed for deploy=", self.service)

    def test_activation_reads_authoritative_revision_not_legacy_projection(self):
        self.assertIn("get_authoritative_deploy(service)", self.service)
        self.assertNotIn("get_active_deploy(service)", self.service.split("def _activate_deployment", 1)[1].split("result = self._process_deployment", 1)[0])


    def test_activation_rechecks_deploy_cancellation_before_commit(self):
        activation = self.service.split("def _activate_deployment", 1)[1].split(
            "result = self._process_deployment", 1
        )[0]
        self.assertIn("current_deploy = Deploy.objects.select_for_update().get(pk=deploy_item.pk)", activation)
        self.assertIn("current_deploy.cancel_requested", activation)
        self.assertIn("Deployment cancellation was requested before activation.", activation)

    def test_stop_intent_is_fenced_before_celery_execution(self):
        runtime_api = (ROOT / "services/api/runtime.py").read_text()
        stop_endpoint = runtime_api.split("def stop_service_apiview", 1)[1].split("def _force_cancel_runtime_cleanup", 1)[0]
        self.assertIn("bump_lifecycle(service_item.pk, desired_state=\"stopped\")", stop_endpoint)
        self.assertIn("service_item.lifecycle_generation = lifecycle_generation", stop_endpoint)
        self.assertIn("stop_service.apply_async(", stop_endpoint)

    def test_deploy_worker_does_not_overwrite_lifecycle_intent(self):
        self.assertNotIn("objects.filter(pk=deploy_item.service_id).update(desired_state=\"running\")", self.service)

    def test_native_activation_passes_lifecycle_and_previous_deploy_fences(self):
        state_manager = (ROOT / "deployments/core/state/manager.py").read_text()
        store = (ROOT / "deployments/infrastructure/django_lifecycle.py").read_text()
        self.assertIn("expected_lifecycle_generation", state_manager)
        self.assertIn("expected_previous_deploy_id", state_manager)
        self.assertIn("enforce_previous_deploy", state_manager)
        self.assertIn("get_authoritative_deploy(service)", state_manager)
        self.assertIn("expected_lifecycle_generation=context.expected_lifecycle_generation", store)
        self.assertIn("expected_previous_deploy_id=context.expected_previous_deploy_id", store)
        self.assertIn("enforce_previous_deploy=context.enforce_previous_deploy", store)
        self.assertIn("enforce_previous_deploy=True", self.service)

    def test_runtime_graph_has_no_service_domain_dependency(self):
        graph = (ROOT / "deployments/core/runtime_graph.py").read_text()
        self.assertNotIn("from services.revisioning import", graph)
        self.assertNotIn("from services.", graph)

    def test_initial_failure_has_runtime_cleanup_contract(self):
        lifecycle = (ROOT / "deployments/application/lifecycle.py").read_text()
        self.assertIn("cleanup_attempted", lifecycle)
        self.assertIn("runtime.remove", lifecycle)
        self.assertIn("There is no previous release to roll back to", lifecycle)

    def test_activation_is_fenced_by_service_lifecycle_generation(self):
        self.assertIn("expected_lifecycle_generation", self.service)
        self.assertIn("actual_lifecycle_generation != expected_lifecycle_generation", self.service)
        self.assertIn("Service lifecycle changed while this deployment was preparing to activate.", self.service)

    def test_swarm_monitor_compares_runtime_release_to_reusable_release_reference(self):
        active_deploy = self.scheduler.split("def _reconcile_active_deploy_swarm", 1)[1].split(
            "def _reconcile_desired_state", 1
        )[0]
        self.assertIn("release_reference_id", active_deploy)
        self.assertIn("Deploy.release_id", self.scheduler)
        self.assertIn("historical per-attempt UUID", self.scheduler)

    def test_swarm_service_reconciliation_does_not_race_active_deployment(self):
        helper = self.scheduler.split("def _service_has_active_native_deployment", 1)[1].split(
            "def _reconcile_service_runtime_swarm", 1
        )[0]
        reconcile = self.scheduler.split("def _reconcile_service_runtime_swarm", 1)[1].split(
            "def _native_reconciliation_plan", 1
        )[0]
        self.assertIn("ACTIVE_DEPLOY_STATUSES", helper)
        self.assertIn("cancel_requested=False", helper)
        self.assertIn("_service_has_active_native_deployment(service)", reconcile)
        self.assertIn("active_revision can still point to the previous", reconcile)
        self.assertIn("with acquire_service_deployment_lock(service.pk):", reconcile)

    def test_scheduler_stop_carries_lifecycle_generation(self):
        desired = self.scheduler.split("def _reconcile_desired_state", 1)[1].split(
            "def _reconcile_service_runtime", 1
        )[0]
        self.assertIn("expected_lifecycle_generation", desired)
        self.assertIn("stop_service.apply_async(", desired)

    def test_stop_worker_rejects_stale_scheduled_stop(self):
        stop_service = (ROOT / "deployments/celery/services/stop_service.py").read_text()
        self.assertIn("expected_lifecycle_generation", stop_service)
        self.assertIn("Skipping stale stop", stop_service)

    def test_swarm_service_reconciliation_does_not_execute_without_plan(self):
        reconcile = self.scheduler.split("def _reconcile_service_runtime_swarm", 1)[1].split(
            "def _native_reconciliation_plan", 1
        )[0]
        self.assertIn("if plan is not None:", reconcile)
        self.assertIn("no native DeploymentPlan could be reconstructed", reconcile)


    def test_swarm_recovery_uses_revision_activation_boundary(self):
        self.assertIn("activate_revision_locked", self.scheduler)
        self.assertNotIn(
            "active_revision_id=revision.revision_id",
            self.scheduler,
        )

    def test_swarm_recovery_uses_authoritative_deployment_pointer(self):
        self.assertIn("get_authoritative_deploy", self.scheduler)
        recovery = self.scheduler.split("def _recover_stale_running_deploys_swarm", 1)[1].split(
            "def _reconcile_active_deploy", 1
        )[0]
        self.assertNotIn("get_active_deploy(", recovery)

    def test_swarm_recovery_respects_current_desired_state(self):
        recovery = self.scheduler.split("def _recover_stale_running_deploys_swarm", 1)[1].split(
            "def _reconcile_active_deploy", 1
        )[0]
        self.assertIn('desired_state", "stopped")', recovery)
        self.assertIn("Skipping stale Swarm recovery", recovery)

    def test_each_replacement_router_has_deployment_identity(self):
        self.assertIn('router_name=f"{config.name}-deploy-', self.orchestrator)
        self.assertIn('"deployment.id": str(config.labels.get("deployment.id")', self.orchestrator)

    def test_router_priority_and_readiness_healthcheck_are_explicit(self):
        self.assertIn("traefik.http.routers.{self.router_name}.priority", self.container)
        self.assertIn("traefik.http.services.{self.router_name}.loadbalancer.healthcheck.path", self.container)

    def test_swarm_recovery_uses_operation_context_for_all_processes(self):
        orchestrator = self.orchestrator
        self.assertIn("self._swarm_recovery_context", orchestrator)
        self.assertIn("def _recover_swarm_mutations", orchestrator)
        self.assertIn('"swarm_recovery")', orchestrator)
        self.assertIn("runtime.rollback_service(service_name)", orchestrator)
        self.assertIn("runtime.remove(service_name)", orchestrator)
        self.assertNotIn("service.rollback()", orchestrator)

    def test_swarm_cancellation_rolls_back_runtime_mutations(self):
        cancellation = self.orchestrator.split("def _handle_cancellation", 1)[1].split(
            "def _handle_failure", 1
        )[0]
        self.assertIn("self._swarm_recovery_context", cancellation)
        self.assertIn("self._recover_swarm_mutations(", cancellation)
        self.assertIn("snapshot = ContainerSnapshot.empty(config.name)", cancellation)

    def test_swarm_failure_uses_swarm_rollback_or_removal(self):
        orchestrator = self.orchestrator.split("def _handle_failure", 1)[1].split(
            "def _deploy_process_containers", 1
        )[0]
        self.assertIn("self._recover_swarm_mutations(", orchestrator)
        self.assertIn("self._recover_swarm_mutations(", orchestrator)
        self.assertNotIn(
            'if snapshot.image_ref:\n            try:\n                self.logger.warning("rollback", "Starting rollback.',
            orchestrator,
        )

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
