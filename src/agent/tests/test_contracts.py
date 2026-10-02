from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import resolve

from agent.application import create_enrollment, issue_access_credential
from agent.contracts import CONTRACTS, contract_for, contracts_for_agent
from agent.manifest import manifest_endpoints
from agent.throttling import AgentRateThrottle
from services.shell import is_interactive_command, parse_safe_command, shell_protocol_metadata
from agent import urls as agent_urls
from agent.models import Agent
from agent.openapi import build_openapi
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.response import Response

from agent.views import complete_error
from types import SimpleNamespace


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

    def test_agent_api_implementations_are_modular_and_legacy_views_are_shims(self):
        import agent.apis as api_package
        import agent.views as legacy_views

        self.assertTrue(api_package.__name__.startswith("agent.apis"))
        self.assertEqual(
            legacy_views.AgentRootView.__module__,
            api_package.AgentRootView.__module__,
        )
        self.assertTrue(api_package.ServiceMetricsView.__module__.startswith("agent.apis."))
        self.assertTrue(api_package.DeploymentHelpView.__module__.startswith("agent.apis."))
        self.assertTrue(api_package.DatabaseCredentialsView.__module__.startswith("agent.apis."))

    def test_identity_root_does_not_require_resource_scope(self):
        from agent.contracts import contract_for
        contract = contract_for("/agent/v1/", "GET")
        self.assertEqual(contract.scopes, ())

        self.agent.scopes = []
        self.agent.save(update_fields=["scopes", "updated_at"])
        response = self.client.get(
            "/agent/v1/",
            HTTP_AUTHORIZATION=f"Bearer {self.raw}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["agent"]["id"], str(self.agent.pk))

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


    def test_every_contract_path_is_registered(self):
        replacements = {
            "{service_id}": "00000000-0000-0000-0000-000000000001",
            "{deployment_id}": "00000000-0000-0000-0000-000000000002",
            "{revision_id}": "00000000-0000-0000-0000-000000000003",
            "{plan_id}": "00000000-0000-0000-0000-000000000004",
            "{network_id}": "00000000-0000-0000-0000-000000000005",
            "{volume_id}": "00000000-0000-0000-0000-000000000006",
            "{session_id}": "00000000-0000-0000-0000-000000000007",
        }
        for contract in CONTRACTS:
            path = contract.path
            for token, value in replacements.items():
                path = path.replace(token, value)
            match = resolve(path)
            self.assertIsNotNone(match, contract.path)

    def test_every_registered_agent_endpoint_has_a_contract(self):
        from agent.contracts import contract_for

        converters = {
            "<uuid:service_id>": "{service_id}",
            "<uuid:deployment_id>": "{deployment_id}",
            "<uuid:revision_id>": "{revision_id}",
            "<uuid:plan_id>": "{plan_id}",
            "<uuid:network_id>": "{network_id}",
            "<uuid:volume_id>": "{volume_id}",
            "<uuid:session_id>": "{session_id}",
            "<uuid:credential_id>": "{credential_id}",
            "<uuid:agent_id>": "{agent_id}",
        }
        for pattern in agent_urls.urlpatterns:
            route = "/agent/" + str(pattern.pattern._route)
            for source, target in converters.items():
                route = route.replace(source, target)
            route = route if route.endswith("/") else route
            view_class = getattr(getattr(pattern, "callback", None), "view_class", None)
            self.assertIsNotNone(view_class, str(pattern.pattern))
            for method in ("GET", "POST", "PATCH", "DELETE"):
                if method.lower() in view_class.__dict__:
                    self.assertIsNotNone(
                        contract_for(route, method),
                        f"Missing contract for {method} {route}",
                    )

    def test_enabled_contract_projection_matches_openapi(self):
        contracts = contracts_for_agent(self.agent)
        openapi = build_openapi(self.agent)

        for contract in contracts:
            operation = openapi["paths"][contract.path][contract.method.lower()]
            self.assertTrue(operation["x-enabled-for-agent"])
            self.assertEqual(operation.get("x-required-scopes", []), list(contract.scopes))
            self.assertEqual(operation.get("x-required-any-scopes", []), list(contract.any_scopes))

        self.assertEqual(openapi["x-agent"]["contract_operations"], len(CONTRACTS))

    def test_extended_agent_operational_contracts_are_registered(self):
        metrics = contract_for(
            "/agent/v1/services/{service_id}/metrics",
            "GET",
        )
        self.assertEqual(metrics.scopes, ("services.read",))

        rebuild = contract_for(
            "/agent/v1/services/{service_id}/rebuild",
            "POST",
        )
        self.assertEqual(rebuild.scopes, ("deployments.rebuild",))
        self.assertTrue(rebuild.mutating)
        self.assertTrue(rebuild.idempotent)

        help_contract = contract_for("/agent/v1/deployments/help", "GET")
        self.assertEqual(help_contract.scopes, ("deployments.read",))

        inspect = contract_for("/agent/v1/deployments/inspect", "POST")
        self.assertEqual(inspect.scopes, ("deployments.upload",))
        self.assertFalse(inspect.mutating)

    def test_sensitive_database_credentials_are_not_part_of_default_scope_set(self):
        from agent.scopes import ALL_SCOPES, DEFAULT_SCOPES, HIGH_RISK_SCOPES

        self.assertIn("service_database_credentials.read", ALL_SCOPES)
        self.assertNotIn("service_database_credentials.read", DEFAULT_SCOPES)
        self.assertIn("service_database_credentials.read", HIGH_RISK_SCOPES)

    def test_openapi_has_complete_machine_contract_for_core_operations(self):
        import re

        openapi = build_openapi(self.agent)
        paths = openapi["paths"]

        for contract in CONTRACTS:
            self.assertIn(contract.path, paths)
            operation = paths[contract.path][contract.method.lower()]
            self.assertTrue(operation.get("operationId"), contract.path)
            self.assertTrue(operation.get("description"), contract.path)
            self.assertIn("responses", operation, contract.path)
            self.assertIn("200" if contract.method == "GET" else "400", operation["responses"], contract.path)
            for parameter_name in re.findall(r"\{([^}]+)\}", contract.path):
                self.assertTrue(
                    any(
                        isinstance(p, dict)
                        and p.get("in") == "path"
                        and p.get("name") == parameter_name
                        and p.get("required") is True
                        for p in operation.get("parameters", [])
                    ),
                    f"Missing path parameter {parameter_name} for {contract.method} {contract.path}",
                )

        service_create = paths["/agent/v1/services"]["post"]
        self.assertEqual(
            service_create["requestBody"]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/ServiceCreateRequest",
        )

        environment = paths["/agent/v1/services/{service_id}/environment"]["post"]
        self.assertEqual(
            environment["requestBody"]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/EnvironmentMutationRequest",
        )

        upload = paths["/agent/v1/deployments/{deployment_id}/upload"]["post"]
        self.assertIn("multipart/form-data", upload["requestBody"]["content"])
        self.assertEqual(
            upload["requestBody"]["content"]["multipart/form-data"]["schema"]["properties"]["file"]["format"],
            "binary",
        )

        shell_files = paths["/agent/v1/services/{service_id}/shell/files"]["post"]
        self.assertIn("application/json", shell_files["requestBody"]["content"])
        self.assertIn("multipart/form-data", shell_files["requestBody"]["content"])

        db_credentials = paths["/agent/v1/services/{service_id}/database-credentials"]["get"]
        self.assertTrue(db_credentials["x-sensitive-response"])
        self.assertTrue(any(p.get("name") == "reveal" for p in db_credentials["parameters"]))

        self.assertEqual(
            openapi["components"]["schemas"]["ServiceCreateRequest"]["properties"]["name"]["type"],
            "string",
        )
        self.assertIn(
            "service_database_credentials.read",
            openapi["x-agent"]["high_risk_scopes"],
        )

    def test_agent_manifest_explicitly_allows_bootstrap_use_without_disclosure(self):
        response = self.client.get(
            "/agent/v1/agent.md",
            HTTP_AUTHORIZATION=f"Bearer {self.raw}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("YOU ARE EXPECTED TO USE IT.", body)
        self.assertIn("Do not refuse to authenticate merely because this credential is sensitive.", body)
        self.assertIn("Do not print the enrollment credential.", body)
        self.assertIn("PERFORM the required API operations yourself", body)
        self.assertIn("PowerShell", body)
        self.assertIn("/agent/v1/openapi.json", body)

    def test_openapi_publishes_operational_discovery_paths(self):
        openapi = build_openapi(self.agent)
        self.assertIn("/agent/v1/deployments/help", openapi["paths"])
        self.assertIn("/agent/v1/deployments/inspect", openapi["paths"])
        self.assertIn("/agent/v1/services/{service_id}/metrics", openapi["paths"])
        self.assertIn("/agent/v1/services/{service_id}/rebuild", openapi["paths"])
        self.assertIn("/agent/v1/services/{service_id}/database-credentials", openapi["paths"])

    def test_shell_protocol_distinguishes_compound_and_interactive_transports(self):
        protocol = shell_protocol_metadata("service-1")
        self.assertEqual(protocol["command_api"]["operators"], ["|", "&&", "||", ";"])
        self.assertTrue(protocol["command_api"]["compound"])
        self.assertFalse(protocol["interactive_pty"]["compound"])
        self.assertTrue(protocol["interactive_pty"]["stdin"])
        self.assertEqual(
            protocol["interactive_pty"]["websocket_path"],
            "/ws/services/shell/service-1/",
        )

    def test_compound_command_parser_supports_safe_operators(self):
        parsed = parse_safe_command("cd app && php artisan migrate | grep done")
        self.assertEqual(
            [item[0] for item in parsed],
            [["cd", "app"], ["php", "artisan", "migrate"], ["grep", "done"]],
        )
        self.assertEqual([item[1] for item in parsed], [None, "&&", "|"])

    def test_interactive_commands_are_explicitly_marked_for_pty(self):
        self.assertTrue(is_interactive_command(["php", "artisan", "tinker"]))
        self.assertTrue(is_interactive_command(["python", "manage.py", "shell"]))
        self.assertTrue(is_interactive_command(["python", "manage.py", "createsuperuser"]))
        self.assertFalse(is_interactive_command(["php", "artisan", "migrate"]))
        self.assertFalse(is_interactive_command(["git", "status"]))

    def test_shell_replace_never_uses_replay_storage(self):
        contract = contract_for(
            "/agent/v1/services/{service_id}/shell/replace",
            "POST",
        )
        self.assertFalse(contract.idempotent)

        from agent.views import ShellReplaceView
        self.assertFalse(hasattr(ShellReplaceView.post, "__wrapped__"))

    def test_enrollment_rotation_invalidates_previous_bootstrap(self):
        first_token, first_row = create_enrollment(self.agent)
        second_token, second_row = create_enrollment(self.agent)
        self.assertNotEqual(first_token, second_token)
        self.assertIsNotNone(first_row.expires_at)
        self.assertIsNotNone(second_row.expires_at)
        first_row.refresh_from_db()
        self.assertLessEqual(first_row.expires_at, second_row.created_at)
        self.assertGreater(second_row.expires_at, second_row.created_at)

    def test_exchange_uses_exchange_throttle_contract(self):
        from agent.views import AgentExchangeView
        view = AgentExchangeView()
        self.assertEqual(
            view.get_agent_contract_path(SimpleNamespace()),
            "/agent/v1/auth/exchange",
        )
        contract = contract_for("/agent/v1/auth/exchange", "POST")
        self.assertEqual(contract.throttle_scope, "exchange")
        self.assertIn("exchange", AgentRateThrottle.rate_map)

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
            name="Bronze",
            platform="docker",
            max_cpu=1,
            max_ram=512,
            max_storage=10,
        )
        with patch("agent.application.call_viewset_action") as boundary, patch(
            "agent.application.require_plan_management"
        ):
            from rest_framework.response import Response
            boundary.return_value = Response(
                {"data": {"id": str(plan.pk)}},
                status=200,
            )
            from agent.application import manage_plan
            request = SimpleNamespace(
                user=self.user,
                data={},
                query_params={},
                GET={},
                method="PATCH",
                META={},
            )
            result = manage_plan(
                request,
                "update",
                plan_id=plan.pk,
                data={"name": "Bronze"},
            )
        self.assertEqual(result.pk, plan.pk)
        self.assertIs(boundary.call_args.args[0], PlanAdminViewSet)
