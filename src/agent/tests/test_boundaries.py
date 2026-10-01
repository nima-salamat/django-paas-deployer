from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIClient

from agent.application import issue_access_credential
from agent.models import Agent


class AgentBoundaryTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.user=User.objects.create_user(username="api_user",email="api_user@example.com",password="example-password")
        self.agent=Agent.objects.create(
            user=self.user,name="api-agent",
            scopes=["services.read","deployments.read","deployments.logs.read","service_logs.read"],
        )
        _,self.raw=issue_access_credential(self.agent)
        self.client=APIClient()

    def test_status_calls_existing_runtime_boundary(self):
        service=Mock()
        service.pk="00000000-0000-0000-0000-000000000001"
        with patch("agent.views.get_service",return_value=service) as getter, patch(
            "agent.application.call_api_view_handler",return_value=Response({"status":"running"})
        ) as delegated:
            response=self.client.get(
                f"/agent/v1/services/{service.pk}/status",
                HTTP_AUTHORIZATION=f"Bearer {self.raw}",
            )
        self.assertEqual(response.status_code,200)
        getter.assert_called_once()
        delegated.assert_called_once()

    def test_runtime_logs_remain_runtime_source(self):
        service=Mock()
        service.pk="00000000-0000-0000-0000-000000000001"
        data={"events":[{"ts":"2026-10-02T00:00:00Z","stream":"stdout","level":"info","message":"hello","cursor":"c"}]}
        with patch("agent.views.get_service",return_value=service), patch("agent.views.runtime_logs",return_value=data):
            response=self.client.get(
                f"/agent/v1/services/{service.pk}/logs",
                HTTP_AUTHORIZATION=f"Bearer {self.raw}",
            )
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["source"],"runtime")
        self.assertEqual(response.data["events"][0]["source"],"runtime")

    def test_openapi_advertises_no_git_or_existing_image(self):
        response=self.client.get("/agent/v1/openapi.json",HTTP_AUTHORIZATION=f"Bearer {self.raw}")
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.data["x-agent"]["deployment_inputs"]["git"])
        self.assertFalse(response.data["x-agent"]["deployment_inputs"]["existing_image"])
