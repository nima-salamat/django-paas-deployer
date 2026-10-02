from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from agent.models import Agent, AgentCredential


class AgentManagementAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="agent-ui-user", email="agent-ui@example.com", password="password")
        self.other = User.objects.create_user(username="agent-ui-other", email="agent-ui-other@example.com", password="password")
        self.agent = Agent.objects.create(user=self.user, name="deploy-bot", scopes=["services.read"])
        self.other_agent = Agent.objects.create(user=self.other, name="other-bot", scopes=["services.read"])
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_is_owner_scoped(self):
        response = self.client.get("/api/agents/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["id"] for row in response.data["results"]}, {str(self.agent.pk)})

    def test_create_and_duplicate_name(self):
        response = self.client.post("/api/agents/", {"name": "ci-bot", "description": "CI access"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["agent"]["scopes"], sorted(response.data["agent"]["scopes"]))
        duplicate = self.client.post("/api/agents/", {"name": "ci-bot"}, format="json")
        self.assertEqual(duplicate.status_code, 409)

    def test_retrieve_cannot_cross_owner_boundary(self):
        response = self.client.get(f"/api/agents/{self.other_agent.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_issue_token_is_returned_once_and_not_stored_plaintext(self):
        response = self.client.post(f"/api/agents/{self.agent.pk}/credentials/", {"expires_in_days": 10}, format="json")
        self.assertEqual(response.status_code, 201)
        token = response.data["credential"]["token"]
        self.assertTrue(token)
        credential = AgentCredential.objects.get(pk=response.data["credential"]["id"])
        self.assertNotEqual(credential.token_hash, token)

    def test_status_and_revoke(self):
        self.assertEqual(self.client.post(f"/api/agents/{self.agent.pk}/disable/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/agents/{self.agent.pk}/enable/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/agents/{self.agent.pk}/revoke/").status_code, 200)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, Agent.Status.REVOKED)
