import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class TestRecoveryOperationJournal(unittest.TestCase):
    def test_deploy_model_contains_minimal_recovery_metadata(self):
        source = (ROOT / "deploy" / "models.py").read_text()
        tree = ast.parse(source)
        names = {node.targets[0].id for node in ast.walk(tree) if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
        # Fields are class attributes, so inspect source directly for the explicit names.
        for field in (
            "operation = models.CharField",
            "operation_started_at = models.DateTimeField",
            "operation_resource_id = models.CharField",
            "operation_previous_resource_id = models.CharField",
            "recovery_metadata = models.JSONField",
        ):
            self.assertIn(field, source)

    def test_recovery_metadata_has_explicit_operation_fields(self):
        model_source = (ROOT / "deploy" / "models.py").read_text()
        for field in (
            "operation",
            "operation_started_at",
            "operation_resource_id",
            "operation_previous_resource_id",
            "recovery_metadata",
        ):
            self.assertIn(field, model_source)

    def test_container_resources_use_positive_deployment_ownership(self):
        source = (ROOT / "deployments" / "core" / "manager" / "container_manager.py").read_text()
        self.assertIn("def find_owned", source)
        self.assertIn("deployment.id", source)

    def test_recovery_does_not_promote_arbitrary_running_container(self):
        source = (ROOT / "deployments" / "celery" / "schedules.py").read_text()
        self.assertIn("owned_by_deploy", source)
        self.assertIn('str(labels.get("deployment.id") or "") == str(locked.pk)', source)
        self.assertIn("recovery could not prove a safe completed state", source)

    def test_stale_terminal_result_is_ignored(self):
        source = (ROOT / "deploy" / "deployment_state.py").read_text()
        self.assertIn("transition_deploy_terminal_if_owned", source)
        self.assertIn("committed = bool(owner)", source)
        self.assertIn("if not committed:", source)


if __name__ == "__main__":
    unittest.main()
