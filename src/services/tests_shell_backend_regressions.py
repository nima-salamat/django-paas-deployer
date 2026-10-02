from pathlib import Path

ROOT = Path(__file__).resolve().parent
API_SHELL = (ROOT / "api" / "shell.py").read_text()
USER_SERVICES = (ROOT / "api" / "user_services.py").read_text()
SHARING = (ROOT / "api" / "sharing.py").read_text()


def test_shell_file_api_has_safe_upload_probe():
    assert 'if action == "upload":' in API_SHELL
    assert 'kind_probe = container.exec_run(\n                ["/bin/sh", "-c"' in API_SHELL
    assert "16 * 1024 * 1024" in API_SHELL
    assert "FILE_EXISTS" in API_SHELL
    assert "_assert_managed_target_safe" in API_SHELL
    assert "Read-only Docker mount" in API_SHELL


def test_shell_download_is_a_dedicated_authenticated_endpoint():
    assert "def shell_download_apiview" in API_SHELL
    assert 'service = _resolve(request, service_id, action="can_shell")' in API_SHELL
    assert "authenticate_session(service, request.user, token)" in API_SHELL
    assert "container.get_archive(path)" in API_SHELL
    assert 'content_type="application/zip"' in API_SHELL


def test_volume_capabilities_match_enforced_share_actions():
    assert "def service_volume_capabilities_apiview" in USER_SERVICES
    assert '"can_volume_attach"' in USER_SERVICES
    assert '"can_volume_detach"' in USER_SERVICES
    assert '"can_volume_add"' in USER_SERVICES
    assert '"can_volume_delete"' in USER_SERVICES


def test_shared_volume_detach_is_rechecked_on_patch():
    assert 'volume.service, "can_volume_detach"' in USER_SERVICES
    assert "if target_service is None and volume.service_id" in USER_SERVICES


def test_unified_service_search_is_server_side():
    assert 'request.query_params.get("q_search")' in SHARING
    assert "service__name__icontains=search" in SHARING
