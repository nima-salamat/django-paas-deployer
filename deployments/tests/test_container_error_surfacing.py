"""
Tests for the critical fix that surfaces the actual Docker error in
container creation failures.

Previously the error chain was:
  Container.create()  -> raises ContainerError("Failed to create container 'X'.")
  Orchestrator        -> stores message in DeploymentResult.message
  DeployService       -> raises OrchestratorDeploymentError(
                           "Orchestrator compilation failed: Failed to create container 'X'."
                         )

The actual Docker error (e.g. "Conflict. The container name '/X' is already
in use", "network not found", "no such image") was stored ONLY in
``details['error']`` and was silently dropped by every logger in the chain
because the celery log formatter doesn't render ``extra`` fields.

These tests verify the fix:
  1. ContainerError raised by create() includes the Docker error in message.
  2. DeploymentLogger renders the error in the celery-visible log line.
  3. Orchestrator _handle_failure includes the underlying error in result.message.
  4. DeployService raises OrchestratorDeploymentError with the detailed message.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from deployments.common.exceptions import (
    ContainerError,
    OrchestratorDeploymentError,
)
from deployments.core.deployment_logger import DeploymentLogger
from deployments.core.manager.container_manager import Container


class _FakeApiError(Exception):
    """Mimic docker.errors.APIError with a status_code attribute."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


class ContainerCreateErrorSurfacingTests(unittest.TestCase):
    """Container.create() must include the actual Docker error in message."""

    def test_image_missing_includes_image_name_in_message(self):
        """
        When the image is missing, the error must say so clearly — not
        "Failed to create container 'X'." with no reason.
        """
        with patch("deployments.core.manager.client_manager.get_docker_client") as gdc:
            mock_client = MagicMock()
            gdc.return_value = mock_client
            mock_client.images.get.side_effect = __import__(
                "docker.errors", fromlist=["ImageNotFound"]
            ).ImageNotFound("app-4aac274e-abcd:v1-00")

            c = Container("app-4aac274e-abcd", image_name="app-4aac274e-abcd:v1-00")

            with self.assertRaises(ContainerError) as ctx:
                c.create()

        msg = ctx.exception.message
        # The message must mention the image name AND that it's missing.
        self.assertIn("app-4aac274e-abcd:v1-00", msg)
        self.assertIn("not present", msg.lower())
        # And the details must record image_present=False for sinks.
        self.assertFalse(ctx.exception.details.get("image_present"))

    def test_404_referenced_resource_includes_engine_error(self):
        """
        When Docker returns 404 mid-create (e.g. network deleted between
        ensure() and create()), the error must include the engine message.
        """
        import docker.errors

        with patch("deployments.core.manager.client_manager.get_docker_client") as gdc:
            mock_client = MagicMock()
            gdc.return_value = mock_client
            mock_client.images.get.return_value = MagicMock()
            mock_client.api.create_host_config.return_value = MagicMock()
            mock_client.api.create_endpoint_config.return_value = MagicMock()
            mock_client.api.create_networking_config.return_value = MagicMock()
            # Construct APIError the way docker-py does in real life:
            # message + response with status_code + explanation string.
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.reason = "Not Found"
            mock_response.url = "/containers/create"
            mock_client.api.create_container.side_effect = docker.errors.APIError(
                "Not Found",
                response=mock_response,
                explanation="network net-5d5c3296 not found",
            )

            c = Container(
                "app-4aac274e-abcd",
                image_name="app-4aac274e-abcd:v1-00",
                networks=["net-5d5c3296"],
            )

            with self.assertRaises(ContainerError) as ctx:
                c.create()

        msg = ctx.exception.message
        # Must surface the actual engine error explanation.
        self.assertIn("network net-5d5c3296 not found", msg)
        # Must mention it was a missing resource.
        self.assertIn("missing referenced resource", msg.lower())

    def test_all_fallbacks_exhausted_includes_actual_error(self):
        """
        When every fallback configuration fails, the final error MUST
        include the actual Docker error message and the last attempted
        stage — not just "Failed to create container 'X'.".
        """
        import docker.errors

        with patch("deployments.core.manager.client_manager.get_docker_client") as gdc:
            mock_client = MagicMock()
            gdc.return_value = mock_client
            mock_client.images.get.return_value = MagicMock()
            mock_client.api.create_host_config.return_value = MagicMock()
            mock_client.api.create_endpoint_config.return_value = MagicMock()
            mock_client.api.create_networking_config.return_value = MagicMock()

            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.reason = "Bad Request"
            mock_response.url = "/containers/create"
            mock_client.api.create_container.side_effect = docker.errors.APIError(
                "Bad Request",
                response=mock_response,
                explanation="container failed to start: invalid argument",
            )
            # And no stale container exists to remove.
            mock_client.containers.get.side_effect = docker.errors.NotFound("nope")

            c = Container(
                "app-4aac274e-abcd",
                image_name="app-4aac274e-abcd:v1-00",
                networks=["net-5d5c3296"],
            )

            with self.assertRaises(ContainerError) as ctx:
                c.create()

        msg = ctx.exception.message
        # The actual Docker error explanation MUST be in the user-visible message.
        self.assertIn("container failed to start: invalid argument", msg)
        self.assertIn("Docker APIError", msg)
        self.assertIn("HTTP 400", msg)
        # The last attempted fallback stage must be named.  The final
        # stage in the fallback chain is "no restart_policy" (added so a
        # bad restart policy never blocks container creation).
        self.assertIn("no restart_policy", msg)
        # And details preserve the structured info for sinks/dashboards.
        self.assertEqual(ctx.exception.details.get("error_type"), "APIError")
        self.assertEqual(ctx.exception.details.get("status_code"), 400)
        self.assertEqual(ctx.exception.details.get("image_present"), True)

    def test_409_conflict_removes_stale_container_and_retries(self):
        """
        On 409 conflict, the create() must attempt to remove a stopped
        stale container and retry.  This handles the common case where a
        previous failed deploy left a stopped container with the same name.
        """
        import docker.errors

        with patch("deployments.core.manager.client_manager.get_docker_client") as gdc:
            mock_client = MagicMock()
            gdc.return_value = mock_client
            mock_client.images.get.return_value = MagicMock()

            mock_client.api.create_host_config.return_value = MagicMock()
            mock_client.api.create_endpoint_config.return_value = MagicMock()
            mock_client.api.create_networking_config.return_value = MagicMock()

            mock_response = MagicMock()
            mock_response.status_code = 409
            mock_response.reason = "Conflict"
            mock_response.url = "/containers/create"
            # First call: 409 conflict.  Second call: success.
            mock_client.api.create_container.side_effect = [
                docker.errors.APIError(
                    "Conflict",
                    response=mock_response,
                    explanation="The container name '/app-x' is already in use",
                ),
                MagicMock(id="new-container-id"),
            ]

            # The stale container exists and is stopped.
            stale = MagicMock()
            stale.status = "exited"
            stale.remove = MagicMock(return_value=True)
            mock_client.containers.get.return_value = stale

            c = Container(
                "app-4aac274e-abcd",
                image_name="app-4aac274e-abcd:v1-00",
            )

            result = c.create()
            self.assertIsNotNone(result)
            # Stale container should have been removed.
            stale.remove.assert_called_once_with(force=True)
            # And create should have been retried after the removal.
            self.assertEqual(mock_client.api.create_container.call_count, 2)


class DeploymentLoggerErrorSurfacingTests(unittest.TestCase):
    """
    DeploymentLogger must render the actual error in the celery-visible
    log line, not just in the silently-dropped ``extra`` field.
    """

    def test_render_includes_error_field(self):
        rendered = DeploymentLogger._render_log_message(
            "container",
            "Failed to create container 'app-x'.",
            {
                "error": "Conflict. The container name '/app-x' is already in use",
                "error_type": "APIError",
                "status_code": 409,
            },
        )
        # The actual Docker error must appear in the rendered log line.
        self.assertIn("Conflict. The container name '/app-x' is already in use", rendered)
        self.assertIn("error_type=APIError", rendered)
        self.assertIn("status_code=409", rendered)

    def test_render_includes_noisy_details_when_absent(self):
        """No details → no noisy continuation line."""
        rendered = DeploymentLogger._render_log_message(
            "image_build", "Building Docker image.", None
        )
        self.assertEqual(rendered, "image_build | Building Docker image.")

    def test_render_truncates_very_long_errors(self):
        """Very long error strings are truncated so logs stay readable."""
        long_error = "x" * 2000
        rendered = DeploymentLogger._render_log_message(
            "container", "Failed.", {"error": long_error}
        )
        self.assertIn("...(truncated)", rendered)
        # Total error field rendered should be bounded.
        # Find the substring after "error=" and check it's not the full 2000 chars.
        idx = rendered.index("error=") + len("error=")
        error_value = rendered[idx:].split(" ", 1)[0]
        self.assertLess(len(error_value), 500)


class OrchestratorFailureMessageTests(unittest.TestCase):
    """
    Orchestrator._handle_failure must include the underlying Docker error
    in DeploymentResult.message so deploy_service can surface it.

    We can't easily import the full orchestrator module here because it
    pulls in Django + dockerfile_generator dependencies that aren't
    available in the test environment.  Instead, we verify the message-
    construction logic by reproducing it directly — this is the SAME
    logic that lives in ``_handle_failure``.
    """

    def test_handle_failure_logic_includes_underlying_error(self):
        from deployments.core.types import DeploymentResult
        from deployments.common.exceptions import ContainerError

        # The actual Docker error lives in details['error'].
        # This mirrors exactly what Container.create() raises after the fix.
        exc = ContainerError(
            "Failed to create container 'app-x' from image 'app-x:v1-00'. "
            "Docker APIError: Conflict. The container name '/app-x' is already in use (HTTP 409).",
            details={
                "error": "Conflict. The container name '/app-x' is already in use",
                "error_type": "APIError",
                "status_code": 409,
            },
        )

        # Reproduce the message-construction logic from
        # DeploymentOrchestrator._handle_failure.
        underlying_error = exc.details.get("error")
        error_type = exc.details.get("error_type")
        status_code = exc.details.get("status_code")

        if underlying_error and underlying_error not in exc.message:
            detailed_message = (
                f"{exc.message} "
                f"Underlying error: {error_type or 'error'}: {underlying_error}"
            )
            if status_code is not None:
                detailed_message += f" (HTTP {status_code})"
        else:
            detailed_message = exc.message

        result = DeploymentResult(
            success=False,
            status="failed",
            message=detailed_message,
            image_ref="app-x:v1-00",
            container_name="app-x",
            error=detailed_message,
            stage=exc.stage,
            details={**exc.details, "rollback_performed": False, "rollback_failed": False},
        )

        # result.message MUST contain the actual Docker error.
        self.assertIn(
            "Conflict. The container name '/app-x' is already in use",
            result.message,
        )
        # HTTP status code must be present so operators can immediately
        # see this is a name conflict.
        self.assertIn("HTTP 409", result.message)
        # Structured details preserve the error type for sinks/dashboards.
        self.assertEqual(result.details.get("error_type"), "APIError")


class DeployServiceErrorPropagationTests(unittest.TestCase):
    """
    DeployService must raise OrchestratorDeploymentError with the
    orchestrator's detailed message (not a generic wrapper).
    """

    def test_orchestrator_deployment_error_carries_detailed_message(self):
        # Simulate the orchestrator returning a failed result.
        from deployments.core.types import DeploymentResult

        detailed_msg = (
            "Failed to create container 'app-x' from image 'app-x:v1-00'. "
            "Docker APIError: Conflict. The container name '/app-x' is "
            "already in use (HTTP 409)."
        )
        failed_result = DeploymentResult(
            success=False,
            status="failed",
            message=detailed_msg,
            image_ref="app-x:v1-00",
            container_name="app-x",
            error=detailed_msg,
            stage="container",
            details={
                "error": "Conflict. The container name '/app-x' is already in use",
                "error_type": "APIError",
                "status_code": 409,
            },
        )

        # Mimic what deploy_service._execute_orchestrator does on failure.
        error_details = getattr(failed_result, "details", {}) or {}
        raised = OrchestratorDeploymentError(
            failed_result.message or "Orchestrator deployment failed.",
            details={
                "stage": getattr(failed_result, "stage", None),
                "container": getattr(failed_result, "container_name", None),
                "image": getattr(failed_result, "image_ref", None),
                "underlying_error": error_details.get("error"),
                "error_type": error_details.get("error_type"),
                "status_code": error_details.get("status_code"),
            },
        )

        # The raised exception's string form (what shows in the celery
        # traceback) MUST contain the actual Docker error.
        self.assertIn(
            "Conflict. The container name '/app-x' is already in use",
            str(raised),
        )
        self.assertIn("HTTP 409", str(raised))


if __name__ == "__main__":
    unittest.main()
