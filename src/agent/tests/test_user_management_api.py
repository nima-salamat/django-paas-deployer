from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from agent.models import Agent, AgentAuditEvent, AgentCredential
from agent.scopes import DEFAULT_SCOPES


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
        self.assertEqual(response.data["agent"]["scopes"], sorted(DEFAULT_SCOPES))
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

    def test_audit_and_manifest_routes_are_not_captured_by_generic_status_route(self):
        audit_response = self.client.get(f"/api/agents/{self.agent.pk}/audit/")
        self.assertEqual(audit_response.status_code, 200)
        manifest_response = self.client.post(f"/api/agents/{self.agent.pk}/manifest/")
        self.assertEqual(manifest_response.status_code, 200)
        self.assertIn("text/markdown", manifest_response["Content-Type"])
        self.assertEqual(manifest_response["Cache-Control"], "no-store")

    def test_dashboard_created_agents_expose_provisioning_source(self):
        response = self.client.post(
            "/api/agents/",
            {"name": "dashboard-created", "description": "", "scopes": ["services.read"]},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["agent"]["provisioning_source"],
            Agent.ProvisioningSource.DASHBOARD,
        )


    def test_credential_can_be_deleted_manually_and_audit_event_is_retained(self):
        credential_response = self.client.post(
            f"/api/agents/{self.agent.pk}/credentials/",
            {"expires_in_days": 10},
            format="json",
        )
        self.assertEqual(credential_response.status_code, 201)
        credential_id = credential_response.data["credential"]["id"]
        response = self.client.delete(
            f"/api/agents/{self.agent.pk}/credentials/{credential_id}/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["deleted"])
        self.assertFalse(AgentCredential.objects.filter(pk=credential_id).exists())
        self.assertTrue(
            AgentAuditEvent.objects.filter(
                agent=self.agent,
                action="browser.credential.delete",
                resource_id=credential_id,
                success=True,
            ).exists()
        )


    def test_delete_removes_agent_and_all_authentication_material_even_when_revoked(self):
        credential_response = self.client.post(
            f"/api/agents/{self.agent.pk}/credentials/",
            {"expires_in_days": 10},
            format="json",
        )
        self.assertEqual(credential_response.status_code, 201)
        credential = AgentCredential.objects.get(pk=credential_response.data["credential"]["id"])

        self.client.post(f"/api/agents/{self.agent.pk}/revoke/")
        response = self.client.delete(f"/api/agents/{self.agent.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["deleted"])
        self.assertTrue(response.data["credentials_deleted"])

        self.assertFalse(Agent.objects.filter(pk=self.agent.pk).exists())
        self.assertFalse(AgentCredential.objects.filter(pk=credential.pk).exists())
        self.assertEqual(
            self.client.get(f"/api/agents/{self.agent.pk}/").status_code,
            404,
        )

    def test_delete_cannot_cross_owner_boundary(self):
        response = self.client.delete(f"/api/agents/{self.other_agent.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_status_and_revoke(self):
        self.assertEqual(self.client.post(f"/api/agents/{self.agent.pk}/disable/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/agents/{self.agent.pk}/enable/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/agents/{self.agent.pk}/revoke/").status_code, 200)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, Agent.Status.REVOKED)
