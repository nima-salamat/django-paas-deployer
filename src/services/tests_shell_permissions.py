"""Focused regression checks for restricted shell authorization.

These checks are intentionally static/source-level so they can run in CI jobs
that do not boot the full Django application. Runtime API tests should assert
owner access, share can_shell access, denied shared access, expired share, and
revoked permission behavior.
"""
from pathlib import Path


def test_shell_api_uses_can_shell_for_all_mutating_endpoints():
    source = Path(__file__).with_name("api").joinpath("shell.py").read_text()
    assert 'action="can_shell"' in source
    assert '_get_service_for_user_or_share' in source
    assert '_get_service_for_user(request' not in source


def test_share_rules_expose_can_shell():
    source = Path(__file__).with_name("share_permissions.py").read_text()
    assert '"can_shell": False' in source
    assert '"can_shell": "Use restricted service shell"' in source
