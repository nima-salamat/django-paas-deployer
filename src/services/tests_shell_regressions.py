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

def test_volume_update_rechecks_shared_detach_permission():
    source = (ROOT / "api" / "user_services.py").read_text()
    assert 'volume.service, "can_volume_detach"' in source


def test_shell_resolves_catalog_wordpress_to_its_real_workspace():
    source = SHELL
    assert '"wordpress": "/var/www/html"' in source
    assert '"wordpress": "wordpress"' in source
    assert 'runtime_config.get("catalog_service_key")' in source


def test_wordpress_shell_does_not_advertise_artisan_commands():
    source = SHELL
    artisan_guard = 'if platform in {"laravel", "php", "generic"}:'
    assert artisan_guard in source
    wordpress_php_guard = 'if platform == "wordpress":'
    assert wordpress_php_guard in source


def test_shell_workspace_metadata_is_importable():
    from services.shell import shell_workspace_metadata

    assert callable(shell_workspace_metadata)

def test_database_workspaces_and_clients_are_engine_aware():
    source = SHELL
    assert '"mysql": "/tmp"' in source
    assert '"mariadb": "/tmp"' in source
    assert '"postgresql": "/tmp"' in source
    assert '"mongodb": "/tmp"' in source
    assert '"redis": "/tmp"' in source
    assert '"oracle": "/tmp"' in source
    assert 'def default_workdir_for_platform' in source
    assert 'DATABASE_DATA_ROOTS' in source
    assert 'def shell_workspace_metadata' in source
    assert 'def _validate_database_argv' in source
    assert 'Database client connections must remain local' in source


def test_database_and_wordpress_interactive_commands_use_pty():
    source = SHELL
    assert '"mysql", "mariadb", "psql", "mongosh", "redis-cli", "sqlplus"' in source
    assert 'str(argv[1]).lower() == "db" and str(argv[2]).lower() == "cli"' in source
    assert 'mysql -uroot' in source
    assert 'wp db cli' in source


def test_managed_database_credentials_are_injected_without_commandline_passwords():
    source = SHELL
    assert 'env["MYSQL_PWD"] = password' in source
    assert 'env["PGPASSWORD"] = password' in source
    assert 'env["REDISCLI_AUTH"] = password' in source
    assert 'Do not put database passwords in command arguments.' in source


def test_command_catalog_source_has_no_stray_wordpress_block():
    source = SHELL
    assert source.count('_catalog_item("wp --info", "Check WP-CLI availability")') == 1
    assert source.count('if platform == "wordpress":') == 1


def test_database_client_commands_are_accepted_per_engine():
    from services.shell import (
        _validate_platform_command,
        default_workdir_for_platform,
    )

    commands = {
        "mysql": ["mysql", "-uroot"],
        "mariadb": ["mariadb", "-uroot"],
        "postgresql": ["psql"],
        "mongodb": ["mongosh"],
        "redis": ["redis-cli"],
        "oracle": ["sqlplus", "/nolog"],
    }
    for platform, argv in commands.items():
        _validate_platform_command(
            argv,
            platform,
            default_workdir_for_platform(platform),
        )


def test_database_client_password_and_remote_execution_are_rejected():
    from services.shell import _validate_platform_command, default_workdir_for_platform

    cases = [
        ("mysql", ["mysql", "-pSuperSecret"]),
        ("mariadb", ["mariadb", "--password=SuperSecret"]),
        ("postgresql", ["psql", "-c", "SELECT 1"]),
        ("mongodb", ["mongosh", "mongodb://10.0.0.5:27017"]),
        ("oracle", ["sqlplus", "system/password@remote"]),
    ]
    for platform, argv in cases:
        try:
            _validate_platform_command(
                argv,
                platform,
                default_workdir_for_platform(platform),
            )
        except Exception:
            continue
        raise AssertionError(f"Unsafe DB command was accepted: {platform} {argv}")

def test_database_diagnostic_commands_are_allowed_per_engine():
    from services.shell import _validate_platform_command, default_workdir_for_platform

    commands = {
        "mysql": ["mysqladmin", "ping", "-uroot"],
        "mariadb": ["mariadb-admin", "ping", "-uroot"],
        "postgresql": ["pg_isready"],
    }
    for platform, argv in commands.items():
        _validate_platform_command(argv, platform, default_workdir_for_platform(platform))


def test_postgresql_remote_connection_string_is_rejected():
    from services.shell import _validate_platform_command, default_workdir_for_platform
    unsafe = ["psql", "postgresql://user@10.0.0.5:5432/db"]
    try:
        _validate_platform_command(unsafe, "postgresql", default_workdir_for_platform("postgresql"))
    except Exception:
        return
    raise AssertionError("Remote PostgreSQL connection string was accepted")

def test_shell_api_imports_workspace_metadata():
    import services.api.shell as shell_api

    assert callable(shell_api.shell_info_apiview)
    assert callable(shell_api.shell_catalog_apiview)


def test_database_restricted_workspace_is_not_a_data_directory():
    from services.shell import (
        default_workdir_for_platform,
        runtime_workdir_for_platform,
    )

    assert default_workdir_for_platform("mysql") == "/tmp"
    assert default_workdir_for_platform("mariadb") == "/tmp"
    assert default_workdir_for_platform("postgresql") == "/tmp"
    assert default_workdir_for_platform("mongodb") == "/tmp"
    assert default_workdir_for_platform("redis") == "/tmp"
    assert default_workdir_for_platform("oracle") == "/tmp"

    assert runtime_workdir_for_platform("mysql") == "/"
    assert runtime_workdir_for_platform("mariadb") == "/"
    assert runtime_workdir_for_platform("postgresql") == "/"
    assert runtime_workdir_for_platform("mongodb") == "/"
    assert runtime_workdir_for_platform("redis") == "/data"
    assert runtime_workdir_for_platform("oracle") == "/opt/oracle"


def test_developer_shell_security_contract_is_explicit():
    source = SHELL
    assert "def developer_shell_security_check" in source
    assert "seccomp=unconfined" in source
    assert "Docker engine access is mounted" in source
    assert "host devices are exposed" in source
    assert '"developer": "developer"' in source
