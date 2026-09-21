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
