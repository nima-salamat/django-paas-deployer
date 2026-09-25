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
        with patch("deploy.event_pipeline.get_channel_layer", return_value=None):
            pipeline = DeploymentEventPipeline(deploy)
        pipeline.channel_layer = None
        return pipeline

    @patch("deploy.event_pipeline.DeployLog.objects")
    def test_record_persists_sanitized_log_and_returns_ui_payload(self, objects):
        created_log = SimpleNamespace(pk="log-1")
        objects.using.return_value.create.return_value = created_log
        pipeline = self.make_pipeline()

        payload = pipeline.record(
            DeploymentEvent(
                stage="validation",
                message="validated token=secret-value",
                progress=10,
                details={"authorization": "Bearer secret-value", "safe": "ok"},
            )
        )

        self.assertEqual(payload["id"], "log-1")
        self.assertEqual(payload["event"], "deployment.validation.info")
        self.assertEqual(payload["message"], "validated token=[REDACTED]")
        self.assertEqual(payload["details"]["authorization"], "[REDACTED]")
        objects.using.assert_called_once_with("deployment_logs")
        objects.using.return_value.create.assert_called_once()

    @patch("deploy.event_pipeline.DeployLog.objects")
    def test_record_does_not_raise_when_log_database_fails(self, objects):
        objects.using.return_value.create.side_effect = OperationalError("log database unavailable")
        pipeline = self.make_pipeline()

        payload = pipeline.record(DeploymentEvent(stage="image", message="building image"))

        self.assertEqual(payload["deployment_id"], "deploy-1")
        self.assertEqual(payload["message"], "building image")

    @patch("deploy.event_pipeline.async_to_sync")
    @patch("deploy.event_pipeline.DeployLog.objects")
    def test_record_publishes_to_deployment_group_when_channel_layer_exists(self, objects, async_to_sync):
        objects.using.return_value.create.return_value = SimpleNamespace(pk="log-2")
        sender = Mock()
        async_to_sync.return_value = sender
        pipeline = self.make_pipeline()
        pipeline.channel_layer = Mock()

        payload = pipeline.record(DeploymentEvent(stage="health", message="healthy", progress=100))

        async_to_sync.assert_called_once_with(pipeline.channel_layer.group_send)
        sender.assert_called_once_with(
            "deploy_deploy-1",
            {"type": "deployment.message", "payload": payload},
        )
