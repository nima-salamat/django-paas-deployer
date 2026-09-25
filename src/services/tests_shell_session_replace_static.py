from pathlib import Path


def test_replace_endpoint_and_permission_are_present():
    api = Path(__file__).with_name("api").joinpath("shell.py").read_text()
    urls = Path(__file__).with_name("urls.py").read_text()
    perms = Path(__file__).with_name("share_permissions.py").read_text()
    assert 'def shell_replace_apiview' in api
    assert '"code": "SHELL_SESSION_ACTIVE"' in api
    assert 'confirm=true is required' in api
    assert 'name="service_shell_replace"' in urls
    assert '"can_shell_replace": False' in perms
