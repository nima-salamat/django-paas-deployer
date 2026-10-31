from unittest.mock import patch
from uuid import uuid4
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from agent.application import issue_access_credential
from agent.models import Agent
from agent.contracts import contract_for


class AgentEfficiencyContractTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="efficiency-user",
            email="efficiency@example.com",
            password="example-password",
        )
        self.agent = Agent.objects.create(
            user=self.user,
            name="efficiency-agent",
            scopes=[
                "services.read",
                "shell.read",
                "shell.execute",
                "shell.files.read",
                "shell.files.write",
            ],
        )
        _, self.raw = issue_access_credential(self.agent)
        self.client = APIClient()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw}"}

    def test_context_combines_identity_and_supports_etag(self):
        first = self.client.get("/agent/v1/context", **self._auth())
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["api_version"], "v1")
        self.assertEqual(first.data["agent"]["id"], str(self.agent.pk))
        self.assertIn("capabilities", first.data)
        self.assertIn("skills", first.data)
        self.assertNotIn("operations", first.data["capabilities"])
        self.assertGreater(first.data["discovery"]["available_operations"], 0)
        self.assertFalse(first.data["discovery"]["operations_included"])
        self.assertTrue(first["ETag"])
        self.assertIn("private", first["Cache-Control"])

        second = self.client.get(
            "/agent/v1/context",
            HTTP_IF_NONE_MATCH=first["ETag"],
            **self._auth(),
        )
        self.assertEqual(second.status_code, 304)
        self.assertEqual(second["ETag"], first["ETag"])

    def test_efficiency_endpoints_are_in_central_contract_and_openapi(self):
        from agent.openapi import build_openapi

        expected = {
            ("GET", "/agent/v1/context"),
            ("GET", "/agent/v1/services/{service_id}/workspace/tree"),
            ("POST", "/agent/v1/services/{service_id}/workspace/read-many"),
            ("POST", "/agent/v1/services/{service_id}/workspace/write-many"),
            ("POST", "/agent/v1/services/{service_id}/workspace/patch"),
            ("POST", "/agent/v1/services/{service_id}/workspace/search"),
            ("POST", "/agent/v1/services/{service_id}/commands/batch"),
            ("POST", "/agent/v1/services/{service_id}/mcp"),
        }
        for method, path in expected:
            self.assertIsNotNone(contract_for(path, method), (method, path))

        document = build_openapi(self.agent)
        for _, path in expected:
            self.assertIn(path, document["paths"])
        self.assertEqual(
            contract_for("/agent/v1/services/{service_id}/workspace/patch", "POST").scopes,
            ("shell.files.write",),
        )
        self.assertTrue(
            contract_for("/agent/v1/services/{service_id}/workspace/patch", "POST").idempotent
        )

    def test_context_can_include_operations_only_when_requested(self):
        response = self.client.get(
            "/agent/v1/context?include=operations",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["discovery"]["operations_included"])
        self.assertTrue(response.data["capabilities"]["operations"])
        self.assertEqual(
            len(response.data["capabilities"]["operations"]),
            response.data["discovery"]["available_operations"],
        )

    def test_context_can_bundle_first_service_page(self):
        response = self.client.get("/agent/v1/context?include=services", **self._auth())
        self.assertEqual(response.status_code, 200)
        self.assertIn("services", response.data["included"])
        self.assertIn("services", response.data)
        self.assertEqual(response.data["cache"]["max_age_seconds"], 5)

    def test_context_contract_does_not_need_resource_scopes(self):
        self.agent.scopes = []
        self.agent.save(update_fields=["scopes", "updated_at"])
        response = self.client.get("/agent/v1/context?include=services", **self._auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["agent"]["scopes"], [])
        self.assertEqual(response.data["omitted"][0]["name"], "services")
        self.assertNotIn("services", response.data)

    def test_mcp_tools_list_uses_agent_scopes_and_returns_jsonrpc(self):
        service_id = uuid4()
        headers = {
            **self._auth(),
            "HTTP_ACCEPT": "application/json, text/event-stream",
            "HTTP_MCP_PROTOCOL_VERSION": "2025-11-25",
            "HTTP_MCP_METHOD": "tools/list",
        }
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        }
        with (
            patch("agent.apis.efficiency.get_service", return_value=SimpleNamespace(user_id=self.user.id)),
            patch("agent.runtime_tools.tools_for_service", return_value=[]),
        ):
            response = self.client.post(
                f"/agent/v1/services/{service_id}/mcp",
                body,
                format="json",
                **headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["jsonrpc"], "2.0")
        self.assertEqual(response.data["id"], 1)
        names = {item["name"] for item in response.data["result"]["tools"]}
        self.assertIn("workspace.read_many", names)
        self.assertIn("workspace.patch", names)
        self.assertIn("command.batch", names)
        self.assertIn("shell.session.create", names)
        self.assertIn("shell.session.close", names)

    def test_read_many_does_not_publish_hash_for_truncated_file(self):
        from types import SimpleNamespace
        from rest_framework.response import Response
        from agent.apis.efficiency import WorkspaceReadManyView

        request = SimpleNamespace(
            agent=self.agent,
            user=self.user,
            data={"paths": ["/app/large.py"], "shell_token": "temporary"},
            headers={},
        )
        preview = Response({
            "result": "success",
            "content": "x" * 262144,
            "content_truncated": True,
            "content_bytes": 300000,
            "content_sha256": "a" * 64,
        })
        with patch("agent.apis.efficiency.get_service", return_value=SimpleNamespace(user_id=self.user.id)), \
             patch("agent.apis.efficiency._file_operation", return_value=preview):
            response = WorkspaceReadManyView().post(request, uuid4())

        self.assertEqual(response.data["files"][0]["ok"], False)
        self.assertTrue(response.data["files"][0]["content_truncated"])
        self.assertEqual(response.data["files"][0]["error"]["code"], "FILE_TOO_LARGE")
        self.assertNotIn("sha256", response.data["files"][0])

    def test_read_many_rejects_non_utf8_files(self):
        from types import SimpleNamespace
        from rest_framework.response import Response
        from agent.apis.efficiency import WorkspaceReadManyView

        request = SimpleNamespace(
            agent=self.agent,
            user=self.user,
            data={"paths": ["/app/image.bin"], "shell_token": "temporary"},
            headers={},
        )
        binary_preview = Response({
            "result": "success",
            "content": "\ufffd",
            "content_utf8": False,
            "content_bytes": 1,
            "content_sha256": "a" * 64,
            "content_truncated": False,
        })
        with patch("agent.apis.efficiency.get_service", return_value=SimpleNamespace(user_id=self.user.id)), \
             patch("agent.apis.efficiency._file_operation", return_value=binary_preview):
            response = WorkspaceReadManyView().post(request, uuid4())

        self.assertEqual(response.data["files"][0]["ok"], False)
        self.assertEqual(response.data["files"][0]["error"]["code"], "FILE_NOT_TEXT")
        self.assertNotIn("sha256", response.data["files"][0])

    def test_mcp_2026_requires_matching_metadata_headers(self):
        service_id = uuid4()
        headers = {
            **self._auth(),
            "HTTP_ACCEPT": "application/json, text/event-stream",
            "HTTP_MCP_PROTOCOL_VERSION": "2026-07-28",
            "HTTP_MCP_METHOD": "tools/list",
        }
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities": {},
                }
            },
        }
        with patch("agent.apis.efficiency.get_service", return_value=SimpleNamespace(user_id=self.user.id)), \
             patch("agent.runtime_tools.tools_for_service", return_value=[]):
            response = self.client.post(
                f"/agent/v1/services/{service_id}/mcp",
                body,
                format="json",
                **headers,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["result"]["resultType"], "complete")
        self.assertEqual(response.data["result"]["_meta"]["io.modelcontextprotocol/serverInfo"]["name"], "PassDeployer")

        headers["HTTP_MCP_METHOD"] = "tools/call"
        with patch("agent.apis.efficiency.get_service", return_value=SimpleNamespace(user_id=self.user.id)):
            mismatch = self.client.post(
                f"/agent/v1/services/{service_id}/mcp",
                body,
                format="json",
                **headers,
            )
        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(mismatch.data["error"]["code"], -32020)
        self.assertEqual(mismatch.data["error"]["data"]["kind"], "HeaderMismatch")

    def test_mcp_origin_validation_rejects_untrusted_origin(self):
        from rest_framework.test import APIRequestFactory
        from agent.apis.efficiency import _valid_mcp_origin

        request = APIRequestFactory().post(
            "/agent/v1/services/example/mcp",
            {},
            format="json",
            HTTP_ORIGIN="https://untrusted.invalid",
            HTTP_HOST="testserver",
        )
        self.assertFalse(_valid_mcp_origin(request))
