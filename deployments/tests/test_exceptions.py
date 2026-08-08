"""
Tests for the unified exception hierarchy.

Verifies that the celery shim re-exports the SAME class as
common.exceptions, so ``except`` clauses can no longer miss a family.
"""

import unittest

from deployments.common import exceptions as common_exc
from deployments.core import exceptions as core_exc
from deployments.celery import exceptions as celery_exc


class TestUnifiedExceptionHierarchy(unittest.TestCase):

    def test_core_module_re_exports_common(self):
        for name in (
            "DeploymentError", "DeploymentValidationError",
            "ContainerError", "ImageBuildError", "HealthCheckError",
            "RollbackError", "DeploymentCancelled",
            "InvalidServiceStateError", "OrchestratorDeploymentError",
            "DeploymentSecurityError",
        ):
            self.assertIs(
                getattr(core_exc, name),
                getattr(common_exc, name),
                f"core.{name} should be the same class as common.{name}",
            )

    def test_celery_module_re_exports_common(self):
        for name in (
            "DeploymentValidationError", "InvalidServiceStateError",
            "ContainerTimeoutError", "OrchestratorDeploymentError",
        ):
            self.assertIs(
                getattr(celery_exc, name),
                getattr(common_exc, name),
                f"celery.{name} should be the same class as common.{name}",
            )

    def test_celery_deployment_error_is_subclass(self):
        # Previously CeleryDeploymentError was NOT a DeploymentError subclass.
        # Now it IS, so a single ``except DeploymentError`` catches both.
        self.assertTrue(issubclass(celery_exc.CeleryDeploymentError, common_exc.DeploymentError))

    def test_security_error_is_validation_error(self):
        # Security errors should be permanent (not retryable) and validation
        # in nature so they surface as user-facing.
        self.assertTrue(
            issubclass(common_exc.DeploymentSecurityError, common_exc.DeploymentValidationError)
        )
        err = common_exc.DeploymentSecurityError("bad input")
        self.assertFalse(err.recoverable)
        self.assertEqual(err.stage, "security")

    def test_recoverable_attribute(self):
        # Permanent errors
        self.assertFalse(common_exc.DeploymentValidationError("x").recoverable)
        self.assertFalse(common_exc.InvalidServiceStateError("x").recoverable)
        self.assertFalse(common_exc.RollbackError("x").recoverable)
        # Recoverable errors (transient)
        self.assertTrue(common_exc.ImageBuildError("x").recoverable)
        self.assertTrue(common_exc.NetworkError("x").recoverable)
        self.assertTrue(common_exc.VolumeError("x").recoverable)
        self.assertTrue(common_exc.ContainerError("x").recoverable)
        self.assertTrue(common_exc.HealthCheckError("x").recoverable)

    def test_stage_attribute(self):
        self.assertEqual(common_exc.ImageBuildError("x").stage, "image_build")
        self.assertEqual(common_exc.HealthCheckError("x").stage, "health_check")
        self.assertEqual(common_exc.RollbackError("x").stage, "rollback")
        # Custom stage overrides default
        err = common_exc.ContainerError("x", stage="custom_stage")
        self.assertEqual(err.stage, "custom_stage")


if __name__ == "__main__":
    unittest.main()
