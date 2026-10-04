"""Regression tests for MySQL/MariaDB readiness probing."""

from deployments.core.db_deployer import (
    _mysql_admin_ping,
    _mysql_exec,
    _mysql_password_auth_clause,
    _reconcile_mysql_credentials,
)


class FakeContainer:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    def exec_run(self, command, environment=None, user=None):
        executable = command[0]
        self.calls.append((executable, command, environment))
        return self.responses[executable]


def test_mariadb_prefers_mariadb_admin():
    container = FakeContainer({
        "mariadb-admin": (0, b"mysqld is alive"),
        "mysqladmin": (0, b"mysqld is alive"),
    })

    ready, output, executable = _mysql_admin_ping(
        container,
        platform="mariadb",
        password="secret",
    )

    assert ready is True
    assert output == "mysqld is alive"
    assert executable == "mariadb-admin"
    assert [call[0] for call in container.calls] == ["mariadb-admin"]
    assert container.calls[0][2] == {"MYSQL_PWD": "secret"}


def test_mariadb_falls_back_when_primary_admin_client_is_missing():
    container = FakeContainer({
        "mariadb-admin": (
            127,
            b'OCI runtime exec failed: exec failed: unable to start container process: exec: "mariadb-admin": executable file not found in $PATH',
        ),
        "mysqladmin": (0, b"mysqld is alive"),
    })

    ready, output, executable = _mysql_admin_ping(
        container,
        platform="mariadb",
        password="secret",
    )

    assert ready is True
    assert output == "mysqld is alive"
    assert executable == "mysqladmin"
    assert [call[0] for call in container.calls] == ["mariadb-admin", "mysqladmin"]


def test_mysql_falls_back_to_mariadb_admin_when_mysqladmin_is_missing():
    container = FakeContainer({
        "mysqladmin": (
            127,
            b'exec: "mysqladmin": executable file not found in $PATH',
        ),
        "mariadb-admin": (0, b"mysqld is alive"),
    })

    ready, output, executable = _mysql_admin_ping(
        container,
        platform="mysql",
        password="secret",
    )

    assert ready is True
    assert output == "mysqld is alive"
    assert executable == "mariadb-admin"
    assert [call[0] for call in container.calls] == ["mysqladmin", "mariadb-admin"]


def test_mariadb_sql_exec_prefers_mariadb_client():
    container = FakeContainer({
        "mariadb": (0, b"1"),
        "mysql": (0, b"1"),
    })

    ok, output = _mysql_exec(
        container,
        "SELECT 1;",
        password="secret",
        platform="mariadb",
    )

    assert ok is True
    assert output == "1"
    assert [call[0] for call in container.calls] == ["mariadb"]
    assert container.calls[0][1][1] == "-uroot"


def test_mariadb_sql_exec_falls_back_to_mysql_when_mariadb_client_is_missing():
    container = FakeContainer({
        "mariadb": (
            127,
            b'exec: "mariadb": executable file not found in $PATH',
        ),
        "mysql": (0, b"1"),
    })

    ok, output = _mysql_exec(
        container,
        "SELECT 1;",
        password="secret",
        platform="mariadb",
    )

    assert ok is True
    assert output == "1"
    assert [call[0] for call in container.calls] == ["mariadb", "mysql"]


def test_mysql_sql_exec_prefers_mysql_client():
    container = FakeContainer({
        "mysql": (0, b"1"),
        "mariadb": (0, b"1"),
    })

    ok, output = _mysql_exec(
        container,
        "SELECT 1;",
        password="secret",
        platform="mysql",
    )

    assert ok is True
    assert output == "1"
    assert [call[0] for call in container.calls] == ["mysql"]


def test_mariadb_password_auth_uses_native_compatible_identified_by_syntax():
    assert (
        _mysql_password_auth_clause("mariadb", "escaped")
        == "IDENTIFIED BY 'escaped'"
    )


def test_mysql_password_auth_keeps_mysql_native_password_syntax():
    assert (
        _mysql_password_auth_clause("mysql", "escaped")
        == "IDENTIFIED WITH mysql_native_password BY 'escaped'"
    )


def test_db_deployer_reconciliation_has_no_direct_hardcoded_mysql_exec():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "core" / "db_deployer.py"
    ).read_text(encoding="utf-8")
    reconciliation = source.split(
        "def _reconcile_mysql_credentials(", 1
    )[1].split(
        "# ============================================================================",
        1,
    )[0]
    assert 'container.exec_run(' not in reconciliation
    assert "_mysql_exec(" in reconciliation
    assert "platform=platform" in reconciliation


class FakeMariaDBCredentialContainer:
    def __init__(self):
        self.calls = []
        self.password_configured = False

    def exec_run(self, command, environment=None, user=None):
        self.calls.append((command, environment, user))
        executable = command[0]
        if executable != "mariadb":
            return 127, b'exec: "mariadb": executable file not found in $PATH'

        protocol = "socket"
        if "--protocol=tcp" in command:
            protocol = "tcp"

        sql = command[-1]
        if protocol == "tcp" and sql == "SELECT 1;" and environment == {"MYSQL_PWD": "new-secret"}:
            if self.password_configured:
                return 0, b"1"
            return 1045, b"ERROR 1045 (28000): Access denied for user 'root'@'localhost' (using password: YES)"

        if protocol == "socket" and sql == "SELECT 1;" and environment is None:
            return 0, b"1"

        if protocol == "socket" and (
            "SET PASSWORD FOR 'root'@'localhost'" in sql
            or "ALTER USER 'root'@'localhost'" in sql
        ):
            self.password_configured = True
            return 0, b""

        return 0, b"1"


def test_mariadb_reconcile_uses_socket_auth_when_configured_password_is_rejected():
    container = FakeMariaDBCredentialContainer()

    ok, message = _reconcile_mysql_credentials(
        client=None,
        container_name="app-mariadb-mariadb",
        root_password="new-secret",
        platform="mariadb",
        container_obj=container,
    )

    assert ok is True, message
    first_command, first_env, first_user = container.calls[0]
    assert first_command[0] == "mariadb"
    assert first_command[1] == "-uroot"
    assert "--protocol=tcp" in first_command
    assert first_env == {"MYSQL_PWD": "new-secret"}
    assert first_user is None
    assert any(
        command[0] == "mariadb"
        and "--protocol=socket" in command
        and command[-1] == "SELECT 1;"
        and environment is None
        for command, environment, _user in container.calls
    )
    assert any(
        "--protocol=socket" in command
        and "CREATE USER IF NOT EXISTS 'root'@'localhost'" in command[-1]
        and environment is None
        and user == "root"
        for command, environment, user in container.calls
    )
    assert any(
        "--protocol=tcp" in command
        and command[-1] == "SELECT 1;"
        and environment == {"MYSQL_PWD": "new-secret"}
        for command, environment, _user in container.calls[1:]
    )


def test_mariadb_reconcile_does_not_use_admin_ping_as_password_proof():
    source = __import__("pathlib").Path(__file__).resolve().parents[1].joinpath("core", "db_deployer.py").read_text(encoding="utf-8")
    reconciliation = source.split("def _reconcile_mysql_credentials(", 1)[1].split(
        "# ============================================================================",
        1,
    )[0]
    first_probe = reconciliation.split("if not root_password_works:", 1)[0]
    assert "root_password_works, root_auth_output = _mysql_exec(" in first_probe
    assert 'protocol="tcp"' in first_probe
    assert 'host="127.0.0.1"' in first_probe
    assert "_mysql_ping_with_password(" not in first_probe


def test_mariadb_root_bootstrap_uses_set_password_and_privileged_socket():
    source = __import__("pathlib").Path(__file__).resolve().parents[1].joinpath("core", "db_deployer.py").read_text(encoding="utf-8")
    reconciliation = source.split("def _reconcile_mysql_credentials(", 1)[1].split(
        "# ============================================================================",
        1,
    )[0]
    assert "SET PASSWORD FOR 'root'@'localhost'" in reconciliation
    assert "SET PASSWORD FOR 'root'@'%'" in reconciliation
    assert 'exec_user="root"' in reconciliation
