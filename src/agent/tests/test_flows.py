from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIClient

from agent.application import issue_access_credential
from agent.models import Agent


class AgentDeploymentAndShellTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.user=User.objects.create_user(username="flow_user",email="flow_user@example.com",password="example-password")
        self.agent=Agent.objects.create(
            user=self.user,
            name="flow-agent",
            scopes=[
                "services.read","deployments.read","deployments.create","deployments.upload",
                "deployments.start","deployments.cancel","deployments.redeploy","deployments.rebuild",
                "deployments.logs.read","service_logs.read","shell.read","shell.execute",
            ],
        )
        _,self.raw=issue_access_credential(self.agent)
        self.client=APIClient()

    def test_deployment_create_uses_existing_viewset_boundary(self):
        fake=Mock()
        fake.pk="00000000-0000-0000-0000-000000000010"
        fake.service_id="00000000-0000-0000-0000-000000000011"
        with patch("agent.views.create_deployment",return_value=fake) as create, patch(
            "agent.views.deployment_payload",return_value={"id":str(fake.pk),"service_id":str(fake.service_id),"status":"queued"}
        ):
            response=self.client.post(
                "/agent/v1/deployments",
                {"service":str(fake.service_id),"source":"archive"},
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {self.raw}",
            )
        self.assertEqual(response.status_code,201)
        create.assert_called_once()

    def test_unsupported_deployment_input_is_not_advertised(self):
        with patch("agent.views.create_deployment",side_effect=__import__("agent.errors",fromlist=["AgentError"]).AgentError("UNSUPPORTED_CAPABILITY","unsupported",status_code=422)):
            response=self.client.post(
                "/agent/v1/deployments",
                {"service":"00000000-0000-0000-0000-000000000011","source":"git"},
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {self.raw}",
            )
        self.assertEqual(response.status_code,422)
        self.assertEqual(response.data["code"],"UNSUPPORTED_CAPABILITY")

    def test_shell_requires_explicit_agent_shell_scope(self):
        self.agent.scopes=["services.read","shell.read"]
        self.agent.save(update_fields=["scopes","updated_at"])
        response=self.client.post(
            "/agent/v1/services/00000000-0000-0000-0000-000000000011/shell/sessions",
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw}",
        )
        self.assertEqual(response.status_code,403)
        self.assertEqual(response.data["code"],"INSUFFICIENT_SCOPE")

    def test_service_logs_and_deployment_logs_have_distinct_sources(self):
        service=Mock()
        service.pk="00000000-0000-0000-0000-000000000011"
        deploy=Mock()
        deploy.pk="00000000-0000-0000-0000-000000000010"
        deploy.service_id=service.pk
        deploy.revision_id=None
        with patch("agent.views.get_service",return_value=service), patch(
            "agent.views.runtime_logs",return_value={"events":[]}
        ), patch("agent.views.get_deployment",return_value=deploy), patch(
            "agent.views.call_api_view_handler",return_value=Response({"logs":[]})
        ):
            runtime=self.client.get(
                f"/agent/v1/services/{service.pk}/logs",
                HTTP_AUTHORIZATION=f"Bearer {self.raw}",
            )
            deployment=self.client.get(
                f"/agent/v1/deployments/{deploy.pk}/logs",
                HTTP_AUTHORIZATION=f"Bearer {self.raw}",
            )
        self.assertEqual(runtime.data["source"],"runtime")
        self.assertEqual(deployment.data["source"],"deployment")
