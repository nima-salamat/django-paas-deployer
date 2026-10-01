from django.contrib.auth import get_user_model
from django.test import TestCase

from agent.application import issue_access_credential
from agent.contracts import CONTRACTS, contract_for, contracts_for_agent
from agent.manifest import manifest_endpoints
from agent.models import Agent
from agent.openapi import build_openapi
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.response import Response

from agent.views import complete_error


class AgentContractTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="contract-user",
            email="contract@example.com",
            password="example-password",
        )
        self.agent = Agent.objects.create(
            user=self.user,
            name="contract-agent",
            scopes=["services.create", "services.read", "plans.apply", "shell.files.write"],
        )
        _, self.raw = issue_access_credential(self.agent)
        self.client = APIClient()

    def test_from_plan_requires_both_scopes_in_runtime_and_openapi(self):
        contract = contract_for("/agent/v1/services/from-plan", "POST")
        self.assertEqual(contract.scopes, ("services.create", "plans.apply"))

        self.agent.scopes = ["services.create"]
        self.agent.save(update_fields=["scopes", "updated_at"])
        response = self.client.post(
            "/agent/v1/services/from-plan",
            {"plan": "00000000-0000-0000-0000-000000000001"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw}",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "INSUFFICIENT_SCOPE")

        openapi = build_openapi(self.agent)
        operation = openapi["paths"]["/agent/v1/services/from-plan"]["post"]
        self.assertEqual(operation["x-required-scopes"], ["services.create", "plans.apply"])
        self.assertFalse(operation["x-enabled-for-agent"])

    def test_shell_close_and_file_operations_use_contract_scopes(self):
        close = contract_for(
            "/agent/v1/services/{service_id}/shell/sessions/{session_id}/close",
            "POST",
        )
        self.assertEqual(close.scopes, ("shell.execute",))

        files = contract_for("/agent/v1/services/{service_id}/shell/files", "POST")
        self.assertEqual(files.any_scopes, ("shell.files.read", "shell.files.write"))

        manifest = manifest_endpoints(self.agent)
        indexed = {(row["method"], row["path"]): row for row in manifest}
        self.assertIn(("POST", "/agent/v1/services/{service_id}/shell/files"), indexed)
        self.assertNotIn(
            ("POST", "/agent/v1/services/{service_id}/shell/sessions/{session_id}/close"),
            indexed,
        )


    def test_sensitive_error_policy_redacts_client_values(self):
        factory = APIRequestFactory()
        request = factory.patch(
            "/agent/v1/services/example/secrets",
            {"key": "DATABASE_PASSWORD", "value": "super-secret-value"},
            format="json",
        )
        request.agent_request_id = "00000000-0000-0000-0000-000000000001"
        response = Response(
            {
                "error": "Validation failed for super-secret-value",
                "errors": {
                    "value": ["super-secret-value"],
                    "token": ["another-secret"],
                    "safe": ["keep-this"],
                },
            },
            status=400,
        )
        sanitized = complete_error(
            response,
            request,
            suppress_sensitive_fields=True,
        )
        body = sanitized.data
        self.assertNotIn("super-secret-value", str(body))
        self.assertEqual(body["errors"]["value"], "[REDACTED]")
        self.assertEqual(body["errors"]["token"], "[REDACTED]")
        self.assertIn("keep-this", str(body))

    def test_enabled_contract_projection_matches_openapi(self):
        contracts = contracts_for_agent(self.agent)
        openapi = build_openapi(self.agent)

        for contract in contracts:
            operation = openapi["paths"][contract.path][contract.method.lower()]
            self.assertTrue(operation["x-enabled-for-agent"])
            self.assertEqual(operation.get("x-required-scopes", []), list(contract.scopes))
            self.assertEqual(operation.get("x-required-any-scopes", []), list(contract.any_scopes))

        self.assertEqual(openapi["x-agent"]["contract_operations"], len(CONTRACTS))

    def test_capabilities_projects_enabled_contracts(self):
        response = self.client.get(
            "/agent/v1/capabilities",
            HTTP_AUTHORIZATION=f"Bearer {self.raw}",
        )
        self.assertEqual(response.status_code, 200)
        enabled = {
            (
                row["method"],
                row["path"],
                tuple(row["required_scopes"]),
                tuple(row["required_any_scopes"]),
            )
            for row in response.data["operations"]
        }
        expected = {
            (
                row.method,
                row.path,
                row.scopes,
                row.any_scopes,
            )
            for row in contracts_for_agent(self.agent)
        }
        self.assertEqual(enabled, expected)

    def test_plan_management_uses_existing_application_boundary(self):
        from unittest.mock import patch
        from plans.models import Plan
        from plans.apis import PlanAdminViewSet
        plan = Plan.objects.create(
            name="contract-plan",
            platform="docker",
            plan_type="custom",
        )
        with patch("agent.application.call_viewset_action") as boundary:
            from rest_framework.response import Response
            boundary.return_value = Response(
                {"data": {"id": str(plan.pk)}},
                status=200,
            )
            from agent.application import manage_plan
            result = manage_plan(
                self.client._request.user if hasattr(self.client, "_request") else self.user,
                "update",
                plan_id=plan.pk,
                data={"name": "contract-plan"},
            )
        self.assertEqual(result.pk, plan.pk)
        self.assertIs(boundary.call_args.args[0], PlanAdminViewSet)
