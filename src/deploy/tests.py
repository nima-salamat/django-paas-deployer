from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import OperationalError
from django.test import SimpleTestCase, override_settings

from deploy.event_pipeline import DeploymentEventPipeline, sanitize
from deployments.core.types import DeploymentEvent


class DeploymentEventSanitizationTests(SimpleTestCase):
    def test_sanitize_redacts_nested_credentials(self):
        payload = {
            "password": "plain-text",
            "nested": {"api_key": "abc123"},
            "logs": ["connecting with token=abc123", "safe message"],
        }

        self.assertEqual(
            sanitize(payload),
            {
                "password": "[REDACTED]",
                "nested": {"api_key": "[REDACTED]"},
                "logs": ["connecting with token=[REDACTED]", "safe message"],
            },
        )


@override_settings(DEPLOYMENT_LOG_DB_ALIAS="deployment_logs")
class DeploymentEventPipelineTests(SimpleTestCase):
    def make_pipeline(self):
        deploy = SimpleNamespace(pk="deploy-1", service_id="service-1")
        return DeploymentEventPipeline(deploy)

    @patch("deploy.event_pipeline.DeploymentEventOutbox.objects")
    def test_record_persists_sanitized_event_to_durable_outbox(self, objects):
        pipeline = self.make_pipeline()

        payload = pipeline.record(
            DeploymentEvent(
                stage="validation",
                message="validated token=secret-value",
                progress=10,
                details={
                    "authorization": "Bearer secret-value",
                    "safe": "ok",
                    "event_type": "deployment.validation.info",
                },
            )
        )

        self.assertEqual(payload["event"], "deployment.validation.info")
        self.assertEqual(payload["message"], "validated token=[REDACTED]")
        self.assertEqual(payload["details"]["authorization"], "[REDACTED]")
        objects.create.assert_called_once()
        event = objects.create.call_args.kwargs
        self.assertEqual(event["deployment_id"], "deploy-1")
        self.assertEqual(event["stage"], "validation")
        self.assertEqual(event["payload"]["details"]["authorization"], "[REDACTED]")
        self.assertEqual(event["event_type"], "deployment.validation.info")

    @patch("deploy.event_pipeline.DeploymentEventOutbox.objects")
    def test_record_does_not_raise_when_outbox_database_fails(self, objects):
        objects.create.side_effect = OperationalError("outbox database unavailable")
        pipeline = self.make_pipeline()

        payload = pipeline.record(DeploymentEvent(stage="image", message="building image"))

        self.assertEqual(payload["deployment_id"], "deploy-1")
        self.assertEqual(payload["message"], "building image")

