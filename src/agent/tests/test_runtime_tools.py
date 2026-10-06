from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import SimpleTestCase


class RuntimeToolRegistryTests(SimpleTestCase):
    def test_wordpress_tools_have_expected_elevation_boundaries(self):
        from agent.runtime_tools import TOOLS

        tools = {tool.name: tool for tool in TOOLS}
        self.assertEqual(tools["wordpress.plugin.manage"].scopes, ("shell.execute",))
        self.assertEqual(tools["wordpress.wp_cli"].scopes, ("shell.execute", "shell.developer"))

    def test_plugin_install_does_not_activate_by_default(self):
        from agent.runtime_tools import _wordpress_plugin_manage

        service = Mock()
        with (
            patch("services.shell._platform_for_service", return_value="wordpress"),
            patch(
                "agent.runtime_tools.command_result_from_argv",
                return_value={"exit_code": 0, "stdout": "", "stderr": "", "risk": "HIGH_IMPACT"},
            ) as execute,
        ):
            result = _wordpress_plugin_manage(service, None, {"action": "install", "slug": "akismet"})

        execute.assert_called_once_with(
            service,
            None,
            ["wp", "plugin", "install", "akismet"],
            confirm=False,
        )
        self.assertEqual(result["action"], "install")
        self.assertEqual(result["slug"], "akismet")

    def test_plugin_install_can_explicitly_activate(self):
        from agent.runtime_tools import _wordpress_plugin_manage

        service = Mock()
        with (
            patch("services.shell._platform_for_service", return_value="wordpress"),
            patch(
                "agent.runtime_tools.command_result_from_argv",
                return_value={"exit_code": 0, "stdout": "", "stderr": "", "risk": "HIGH_IMPACT"},
            ) as execute,
        ):
            _wordpress_plugin_manage(
                service,
                None,
                {"action": "install", "slug": "akismet", "activate": True, "confirm": True},
            )

        execute.assert_called_once_with(
            service,
            None,
            ["wp", "plugin", "install", "akismet", "--activate"],
            confirm=True,
        )
