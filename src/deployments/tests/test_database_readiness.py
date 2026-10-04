"""Regression tests for MySQL/MariaDB readiness probing."""

from deployments.core.db_deployer import _mysql_admin_ping


class FakeContainer:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    def exec_run(self, command, environment=None):
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
