from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from agent.application import issue_access_credential
from agent.models import Agent


class AgentSkillTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="skill-user",
            email="skill@example.com",
            password="example-password",
        )
        self.agent = Agent.objects.create(
            user=self.user,
            name="skill-agent",
            scopes=["services.read", "shell.read", "shell.execute", "shell.files.read", "shell.files.write"],
        )
        _, self.raw = issue_access_credential(self.agent)
        self.client = APIClient()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw}"}

    def test_skill_index_is_scope_filtered(self):
        response = self.client.get("/agent/v1/skills", **self._auth())
        self.assertEqual(response.status_code, 200)
        names = {item["name"] for item in response.data["skills"]}
        self.assertIn("services", names)
        self.assertIn("workspace-files", names)
        self.assertIn("php", names)
        self.assertIn("wordpress", names)
        self.assertIn("databases", names)
        self.assertNotIn("deployments", names)

    def test_skill_detail_returns_markdown(self):
        response = self.client.get("/agent/v1/skills/workspace-files", **self._auth())
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("# Workspace Files", body)
        self.assertIn("/agent/v1/services/{service_id}/shell/files", body)

    def test_wordpress_and_database_skills_return_markdown(self):
        wordpress = self.client.get("/agent/v1/skills/wordpress", **self._auth())
        databases = self.client.get("/agent/v1/skills/databases", **self._auth())
        self.assertEqual(wordpress.status_code, 200)
        self.assertEqual(databases.status_code, 200)
        self.assertIn("# WordPress", wordpress.content.decode())
        self.assertIn("# Databases", databases.content.decode())

    def test_developer_skill_is_scope_filtered(self):
        self.agent.scopes = ["services.read", "shell.read", "shell.execute"]
        self.agent.save(update_fields=["scopes", "updated_at"])
        response = self.client.get("/agent/v1/skills/developer-shell", **self._auth())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "INSUFFICIENT_SCOPE")

    def test_unavailable_skill_is_denied(self):
        response = self.client.get("/agent/v1/skills/deployments", **self._auth())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "INSUFFICIENT_SCOPE")

    def test_unknown_skill_is_not_found(self):
        response = self.client.get("/agent/v1/skills/does-not-exist", **self._auth())
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "SKILL_NOT_FOUND")


    def test_openapi_document_builds_successfully(self):
        response = self.client.get("/agent/v1/openapi.json", **self._auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"].split(";")[0], "application/json")
        self.assertEqual(response.data["openapi"], "3.0.3")
        self.assertIn("/agent/v1/skills", response.data["paths"])
        self.assertIn("/agent/v1/skills/{skill_name}", response.data["paths"])

    def test_manifest_contains_skill_links(self):
        self.agent.scopes.append("agent.manifest.generate")
        self.agent.save(update_fields=["scopes", "updated_at"])
        response = self.client.get("/agent/v1/agent.md", **self._auth())
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("/agent/v1/skills/services", body)
        self.assertIn("/agent/v1/skills/workspace-files", body)


    def test_runtime_tool_skill_and_registry_are_exposed(self):
        response = self.client.get("/agent/v1/skills/runtime-tools", **self._auth())
        self.assertEqual(response.status_code, 200)
        self.assertIn("/agent/v1/services/{service_id}/tools", response.content.decode())

    def test_runtime_tool_openapi_contract_is_present(self):
        response = self.client.get("/agent/v1/openapi.json", **self._auth())
        self.assertEqual(response.status_code, 200)
        self.assertIn("/agent/v1/services/{service_id}/tools", response.data["paths"])
        self.assertIn("/agent/v1/services/{service_id}/tools/{tool_name}", response.data["paths"])
