from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHELL = (ROOT / "shell.py").read_text()
API = (ROOT / "api" / "shell.py").read_text()
FRONT = (ROOT.parent.parent / "../review_current/front/src/components/service_detail/components/ShellPanel.jsx").resolve()


def test_backend_has_container_path_guard_and_realpath_probe():
    assert "def _assert_container_path_within" in SHELL
    assert "readlink -f" in SHELL
    assert "Path resolves outside the service workspace" in SHELL


def test_delete_does_not_use_target_file_write_permission_gate():
    delete_section = API.split('if action == "delete":', 1)[1].split('if action == "rename":', 1)[0]
    assert 'path_access(container, safe_path, for_create=True)' not in delete_section
    assert '_file_manager_exec(container, cmd, workdir=session.workdir)' in delete_section


def test_frontend_completion_uses_full_prefix_and_editor_parser():
    source = FRONT.read_text()
    assert "parseSingleEditorArgument" in source
    assert "prefixBeforeToken" in source
    assert "fullPrefix" in source


def test_frontend_run_command_declares_editor_parser_dependency():
    source = FRONT.read_text()
    assert "isInteractiveCommand, parseSingleEditorArgument, refreshDirectory" in source


def test_service_list_api_declares_creation_order_before_pagination():
    source = (ROOT / "api" / "user_services.py").read_text()
    assert 'order_by("-created_at", "-id")' in source
    assert 'page = self.paginate_queryset(query)' in source
    assert source.index('order_by("-created_at", "-id")') < source.index('page = self.paginate_queryset(query)')


def test_service_list_api_accepts_search_and_status_filters():
    source = (ROOT / "api" / "user_services.py").read_text()
    assert 'request.query_params.get("search")' in source
    assert 'request.query_params.get("status")' in source
    assert 'query = query.filter(status=status_param)' in source

def test_shell_download_is_dedicated_and_streams_single_files():
    source = API
    assert "def shell_download_apiview" in source
    assert "container.get_archive(path)" in source
    assert "FileResponse(output" in source
    assert 'content_type="application/zip"' in source


def test_shell_upload_enforces_filename_collision_size_and_mount_policy():
    source = API
    assert 'if action == "upload":' in source
    assert "16 * 1024 * 1024" in source
    assert "FILE_EXISTS" in source
    assert "_assert_managed_target_safe" in source
    assert "Read-only Docker mount" in source
    assert "container.exec_run(" in source
    assert '["/bin/sh", "-c"' in source

def test_upload_uses_fixed_backend_probe_without_nested_exec_arguments():
    source = API
    assert 'kind_probe = container.exec_run(\n                ["/bin/sh", "-c"' in source
    assert 'can_delete = True' in (ROOT / "api" / "user_services.py").read_text()


def test_unified_services_search_is_server_side_for_all_scopes():
    source = (ROOT / "api" / "sharing.py").read_text()
    assert 'request.query_params.get("q_search")' in source
    assert 'service__name__icontains=search' in source
