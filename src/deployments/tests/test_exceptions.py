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
        # Image build failures are deterministic by default; transient infrastructure
        # callers must opt in explicitly.
        self.assertFalse(common_exc.ImageBuildError("x").recoverable)
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


    def test_user_messages_are_separated_from_technical_messages(self):
        cases = [
            common_exc.ImageBuildError("composer install exited with code 1"),
            common_exc.ContainerError("Docker APIError: conflict"),
            common_exc.HealthCheckError("Container 'app' did not become ready"),
            common_exc.DeploymentValidationError("Invalid PHP version"),
        ]
        for err in cases:
            self.assertNotEqual(err.user_message, err.technical_message)
            self.assertTrue(err.code)
            self.assertTrue(err.category)
            self.assertTrue(err.stage)

    def test_transient_image_build_failure_can_explicitly_opt_in_to_retry(self):
        err = common_exc.ImageBuildError(
            "registry temporarily unavailable",
            recoverable=True,
            details={"transient": True},
        )
        self.assertTrue(err.recoverable)
        self.assertEqual(err.stage, "image_build")

    def test_health_message_is_actionable_but_does_not_require_http_details(self):
        err = common_exc.HealthCheckError(
            "Container 'web' did not become ready before the 60s health-check timeout."
        )
        self.assertIn("did not become ready", err.user_message.lower())
        self.assertIn("health-check", err.technical_message.lower())


if __name__ == "__main__":
    unittest.main()

class TestInternalPlatformErrors(unittest.TestCase):

    def test_unexpected_python_exception_is_non_recoverable_and_sanitized(self):
        err = common_exc.to_deployment_error(
            NameError("name '_paths_cfg' is not defined"),
            stage="prepare",
        )
        self.assertIsInstance(err, common_exc.InternalPlatformError)
        self.assertFalse(err.recoverable)
        self.assertEqual(err.code, "INTERNAL_PLATFORM_ERROR")
        self.assertEqual(err.category, "internal_platform_error")
        self.assertNotEqual(err.user_message, err.technical_message)
        self.assertIn("internal error", err.user_message.lower())
        self.assertEqual(err.technical_message, "name '_paths_cfg' is not defined")

    def test_existing_deployment_error_keeps_classification(self):
        source = common_exc.ImageBuildError("mirror unavailable", recoverable=True)
        self.assertIs(common_exc.to_deployment_error(source), source)
        self.assertTrue(source.recoverable)
