"""
deployments/core/db_deployer.py

Database container deployer for:
    - MySQL
    - MariaDB
    - PostgreSQL
    - MongoDB
    - Redis
    - Oracle

Important MySQL behavior
------------------------
Docker official MySQL environment variables such as:

    MYSQL_ROOT_PASSWORD
    MYSQL_DATABASE
    MYSQL_USER
    MYSQL_PASSWORD

are primarily initialization variables.

If a persistent Docker volume already contains an initialized MySQL
datadir, changing those environment variables does NOT automatically
change existing MySQL users/passwords.

Therefore this deployer does NOT rely only on environment variables.

For MySQL/MariaDB it:

    1. Starts the container.
    2. Waits until mysqld is actually ready.
    3. Connects through the local Unix socket.
    4. Reconciles root credentials.
    5. Creates/updates the requested application user.
    6. Creates the requested database.
    7. Grants the application user access to that database.
    8. Verifies the credentials.

This makes redeploying against an existing persistent volume predictable.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import docker
from docker.errors import APIError, NotFound

from core.global_settings.config import MIRROR_DOCKER
from deployments.core.exceptions import DeploymentError
from deployments.core.manager.client_manager import Client


logger = logging.getLogger(__name__)


# ============================================================================
# Images
# ============================================================================

_DB_IMAGES: dict[str, str] = {
    "mysql": "mysql:8.0.36",
    "mariadb": "mariadb:11",
    "postgresql": "postgres:16-alpine",
    "mongodb": "mongo:7",
    "redis": "redis:7-alpine",
    "oracle": "gvenzl/oracle-xe:21-slim",
}


DB_PLATFORMS: frozenset[str] = frozenset(_DB_IMAGES.keys())


_DEFAULT_PORTS: dict[str, int] = {
    "mysql": 3306,
    "mariadb": 3306,
    "postgresql": 5432,
    "mongodb": 27017,
    "redis": 6379,
    "oracle": 1521,
}


SENSITIVE_CONFIG_KEYS: frozenset[str] = frozenset({
    "password",
    "root_password",
    "username",
})


MUTABLE_DB_CONFIG_KEYS: frozenset[str] = frozenset({
    "root_password",
    "password",
    "username",
    "database",
    "port",
    "env",
})


# ============================================================================
# Result
# ============================================================================

@dataclass
class DBDeployResult:
    success: bool
    message: str
    container_name: str
    platform: str
    port: int | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Helpers
# ============================================================================

def _clean(value: Any) -> str:
    return str(value or "").strip()


def _mysql_identifier(value: str) -> str:
    """
    Escape a MySQL identifier used inside backticks.
    """
    return _clean(value).replace("`", "``")


def _mysql_string(value: str) -> str:
    """
    Escape a MySQL string literal.

    We explicitly escape backslashes and single quotes because passwords
    may contain characters such as:

        '
        \
        $
        !
        "

    Passwords are never logged.
    """
    value = str(value or "")

    return (
        value
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\x00", "")
    )


def _safe_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# ============================================================================
# Environment builders
# ============================================================================

def _mysql_env(cfg: dict[str, Any]) -> dict[str, str]:
    """
    Build environment for MySQL/MariaDB.

    ONLY root credentials (and optional database name) go into env.
    These are used by the official entrypoint solely on FIRST init of
    an empty data volume.

    Application username/password are NEVER passed as env vars.
    They are always created/updated by _reconcile_mysql_credentials
    after the server is ready — same path for new and existing volumes.
    """

    root_password = _clean(
        cfg.get("root_password") or cfg.get("password")
    )
    database = _clean(cfg.get("database"))

    if not root_password:
        raise DeploymentError(
            "MySQL/MariaDB requires a non-empty root_password "
            "(or password).",
            stage="validation",
            details={"platform": "mysql"},
        )

    env: dict[str, str] = {
        "MYSQL_ROOT_PASSWORD": root_password,
        # MariaDB official image also accepts this alias
        "MARIADB_ROOT_PASSWORD": root_password,
    }

    if database:
        env["MYSQL_DATABASE"] = database
        env["MARIADB_DATABASE"] = database

    # MYSQL_USER / MYSQL_PASSWORD intentionally omitted.

    return env


def _postgres_env(cfg: dict[str, Any]) -> dict[str, str]:
    password = _clean(cfg.get("password"))

    if not password:
        raise DeploymentError(
            "PostgreSQL requires a non-empty password.",
            stage="validation",
            details={"platform": "postgresql"},
        )

    env = {
        "POSTGRES_PASSWORD": password,
    }

    username = _clean(cfg.get("username"))
    database = _clean(cfg.get("database"))

    if username:
        env["POSTGRES_USER"] = username

    if database:
        env["POSTGRES_DB"] = database

    return env


def _mongo_env(cfg: dict[str, Any]) -> dict[str, str]:
    username = _clean(cfg.get("username")) or "root"
    password = _clean(cfg.get("password"))

    if not password:
        raise DeploymentError(
            "MongoDB requires a non-empty password.",
            stage="validation",
            details={"platform": "mongodb"},
        )

    env = {
        "MONGO_INITDB_ROOT_USERNAME": username,
        "MONGO_INITDB_ROOT_PASSWORD": password,
    }

    database = _clean(cfg.get("database"))

    if database:
        env["MONGO_INITDB_DATABASE"] = database

    return env


def _redis_env(cfg: dict[str, Any]) -> dict[str, str]:
    return {}


def _oracle_env(cfg: dict[str, Any]) -> dict[str, str]:
    password = _clean(cfg.get("password"))

    if not password:
        raise DeploymentError(
            "Oracle requires a non-empty password.",
            stage="validation",
            details={"platform": "oracle"},
        )

    return {
        "ORACLE_PASSWORD": password,
        "ORACLE_PWD": password,
    }


_ENV_BUILDERS: dict[str, Any] = {
    "mysql": _mysql_env,
    "mariadb": _mysql_env,
    "postgresql": _postgres_env,
    "mongodb": _mongo_env,
    "redis": _redis_env,
    "oracle": _oracle_env,
}


# ============================================================================
# Validation
# ============================================================================

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "mysql": ["root_password"],
    "mariadb": ["root_password"],
    "postgresql": ["password"],
    "mongodb": ["username", "password"],
    "redis": [],
    "oracle": ["password"],
}


def validate_db_config(
    platform: str,
    cfg: dict[str, Any],
) -> list[str]:

    errors: list[str] = []

    if platform not in DB_PLATFORMS:
        return [f"Unsupported database platform '{platform}'."]

    # ------------------------------------------------------------------------
    # MySQL / MariaDB
    # ------------------------------------------------------------------------

    if platform in ("mysql", "mariadb"):

        root_password = _clean(
            cfg.get("root_password") or cfg.get("password")
        )

        if not root_password:
            errors.append(
                "MySQL/MariaDB requires a non-empty "
                "'root_password' or 'password'."
            )

        username = _clean(cfg.get("username"))

        if username:

            if username.lower() == "root":
                errors.append(
                    "Do not use 'root' as the application username. "
                    "Use a separate application user."
                )

            if not _clean(cfg.get("password")) and not root_password:
                errors.append(
                    "A password is required when username is provided."
                )

    # ------------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------------

    elif platform == "postgresql":

        if not _clean(cfg.get("password")):
            errors.append(
                "PostgreSQL requires a non-empty 'password'."
            )

    # ------------------------------------------------------------------------
    # MongoDB
    # ------------------------------------------------------------------------

    elif platform == "mongodb":

        if not _clean(cfg.get("username")):
            errors.append(
                "MongoDB requires 'username'."
            )

        if not _clean(cfg.get("password")):
            errors.append(
                "MongoDB requires 'password'."
            )

    # ------------------------------------------------------------------------
    # Oracle
    # ------------------------------------------------------------------------

    elif platform == "oracle":

        if not _clean(cfg.get("password")):
            errors.append(
                "Oracle requires 'password'."
            )

    # ------------------------------------------------------------------------
    # Port
    # ------------------------------------------------------------------------

    port = cfg.get("port")

    if port is not None:

        try:
            port_int = int(port)

            if not 1 <= port_int <= 65535:
                errors.append(
                    f"port {port_int} is outside valid range 1-65535."
                )

        except (TypeError, ValueError):
            errors.append(
                f"port '{port}' is not a valid integer."
            )

    # ------------------------------------------------------------------------
    # MySQL database name
    # ------------------------------------------------------------------------

    if platform in ("mysql", "mariadb"):

        database = _clean(cfg.get("database"))

        reserved = {
            "mysql",
            "sys",
            "information_schema",
            "performance_schema",
        }

        if database.lower() in reserved:
            errors.append(
                f"database '{database}' is reserved by MySQL/MariaDB."
            )

    return errors


# ============================================================================
# MySQL readiness
# ============================================================================

def _mysql_is_running(
    client,
    container_name: str,
) -> bool:

    try:
        container = client.containers.get(container_name)
        container.reload()

        return container.status == "running"

    except Exception:
        return False




def _mysql_wait_until_ready(
    client,
    container_name: str,
    timeout: int = 240,
    *,
    root_password: str = "",
) -> tuple[bool, str]:
    """
    Wait until the OFFICIAL MySQL Docker entrypoint has completely
    finished initialization and the FINAL mysqld instance is ready.

    IMPORTANT:
    `mysqladmin ping` alone is NOT sufficient because the official
    MySQL entrypoint starts a temporary mysqld during initialization.

    We therefore require:

        1. MySQL initialization to be finished.
        2. Temporary server to have stopped.
        3. Final mysqld to be running.
        4. Final mysqld to answer mysqladmin ping (with root password).

    After the entrypoint sets MYSQL_ROOT_PASSWORD on the temporary
    server, root requires a password.  Ping without MYSQL_PWD then
    fails with Access Denied and the wait would never succeed —
    so we always pass root_password for the final readiness probe.
    """

    import time

    deadline = time.monotonic() + timeout

    last_status = ""
    last_logs = ""

    initialization_finished = False
    temporary_server_stopped = False
    notfound_streak = 0
    root_password = _clean(root_password)

    while time.monotonic() < deadline:

        try:
            container = client.containers.get(
                container_name
            )

            container.reload()

            status = container.status
            last_status = status
            notfound_streak = 0

            # ------------------------------------------------------------
            # Read current logs
            # ------------------------------------------------------------

            try:

                raw_logs = container.logs(
                    tail=250,
                    timestamps=False,
                )

                logs = (
                    raw_logs.decode(
                        "utf-8",
                        "replace",
                    )
                    if isinstance(
                        raw_logs,
                        (bytes, bytearray),
                    )
                    else str(raw_logs or "")
                )

                last_logs = logs

            except Exception:
                logs = last_logs

            logs_lower = logs.lower()

            # ------------------------------------------------------------
            # Detect official initialization completion
            # ------------------------------------------------------------

            init_done = (
                "mysql init process done" in logs_lower
                or
                "mysql init process done." in logs_lower
            )

            if init_done:
                initialization_finished = True

            # ------------------------------------------------------------
            # Detect temporary server shutdown
            # ------------------------------------------------------------

            temporary_stopped = (
                "temporary server stopped" in logs_lower
                or
                "temporary server stop" in logs_lower
            )

            if temporary_stopped:
                temporary_server_stopped = True

            # ------------------------------------------------------------
            # FINAL SERVER readiness
            #
            # We ONLY run mysqladmin ping after the official
            # initialization has finished.  After the entrypoint has
            # applied MYSQL_ROOT_PASSWORD, root requires that password.
            # ------------------------------------------------------------

            if (
                initialization_finished
                and temporary_server_stopped
                and status == "running"
            ):

                try:
                    ping_env = None
                    if root_password:
                        ping_env = {"MYSQL_PWD": root_password}

                    exit_code, output = (
                        container.exec_run(
                            [
                                "mysqladmin",
                                "ping",
                                "-uroot",
                                "--protocol=socket",
                                "--silent",
                            ],
                            environment=ping_env,
                        )
                    )

                    output_text = (
                        output.decode(
                            "utf-8",
                            "replace",
                        )
                        if isinstance(
                            output,
                            (bytes, bytearray),
                        )
                        else str(output or "")
                    )

                    if int(exit_code) == 0:

                        return (
                            True,
                            "MySQL official initialization completed "
                            "and the final MySQL server is ready.",
                        )

                    last_logs = output_text

                except Exception as exc:

                    last_logs = str(exc)

            # ------------------------------------------------------------
            # Do NOT consider the temporary server ready.
            # ------------------------------------------------------------

            if (
                "temporary server started" in logs_lower
                and not initialization_finished
            ):

                time.sleep(1)
                continue

            # ------------------------------------------------------------
            # Container restarting
            # ------------------------------------------------------------

            if status == "restarting":

                time.sleep(1)
                continue

            # ------------------------------------------------------------
            # Created / paused
            # ------------------------------------------------------------

            if status in {
                "created",
                "paused",
            }:

                time.sleep(1)
                continue

            # ------------------------------------------------------------
            # Exited / dead
            # ------------------------------------------------------------

            if status in {
                "exited",
                "dead",
            }:

                restart_policy = {}

                try:

                    restart_policy = (
                        container.attrs
                        .get("HostConfig", {})
                        .get("RestartPolicy", {})
                    )

                except Exception:
                    pass

                restart_name = str(
                    restart_policy.get("Name") or ""
                ).lower()

                if restart_name in {
                    "always",
                    "unless-stopped",
                    "on-failure",
                }:

                    time.sleep(1)
                    continue

                return (
                    False,
                    (
                        f"MySQL container '{container_name}' "
                        f"stopped with status '{status}'.\n\n"
                        f"Last logs:\n"
                        f"{last_logs[-5000:]}"
                    ),
                )

        except NotFound:
            notfound_streak += 1
            if notfound_streak >= 8:
                return (
                    False,
                    (
                        f"MySQL container '{container_name}' "
                        "was removed while waiting for readiness."
                    ),
                )
            time.sleep(1)
            continue

        except Exception as exc:

            last_logs = str(exc)

        time.sleep(1)

    return (
        False,
        (
            f"MySQL official initialization did not complete "
            f"within {timeout} seconds.\n\n"
            f"Status: {last_status}\n\n"
            f"Last logs:\n{last_logs[-5000:]}"
        ),
    )


def _mysql_exec(
    container,
    statement: str,
    *,
    password: str | None = None,
) -> tuple[bool, str]:

    """
    Execute SQL inside the MySQL container.

    The password is passed through MYSQL_PWD instead of putting it
    directly into the command line.

    This avoids:

        mysql -uroot -pPASSWORD

    which would expose the password in process arguments.
    """

    env = None

    if password:
        env = {
            "MYSQL_PWD": password,
        }

    try:

        exit_code, output = container.exec_run(
            [
                "mysql",
                "-uroot",
                "--protocol=socket",
                "--batch",
                "--skip-column-names",
                "-e",
                statement,
            ],
            environment=env,
        )

        text = (
            output.decode(
                "utf-8",
                "replace",
            )
            if isinstance(output, bytes)
            else str(output or "")
        )

        if int(exit_code) == 0:
            return True, text.strip()

        return False, text.strip()

    except Exception as exc:
        return False, str(exc)


def _mysql_ping_with_password(
    container,
    password: str,
) -> bool:

    try:

        exit_code, _ = container.exec_run(
            [
                "mysqladmin",
                "ping",
                "-uroot",
                "--protocol=socket",
                "--silent",
            ],
            environment={
                "MYSQL_PWD": password,
            },
        )

        return int(exit_code) == 0

    except Exception:
        return False


# ============================================================================
# MySQL credential reconciliation
# ============================================================================
def _reconcile_mysql_credentials(
    client,
    container_name: str,
    *,
    root_password: str,
    username: str = "",
    user_password: str = "",
    database: str = "",
) -> tuple[bool, str]:

    """
    Reconcile MySQL credentials against the ACTUAL database state.
    
    CRITICAL FIX: We explicitly use 'mysql_native_password' because MySQL 8.0's
    default 'caching_sha2_password' blocks authentication via Unix Socket
    when using MYSQL_PWD, causing false "Access Denied" errors during verification.
    """

    root_password = _clean(root_password)
    username = _clean(username)
    user_password = _clean(user_password) or root_password
    database = _clean(database)

    if not root_password:
        return False, "root password is empty"

    try:
        container = client.containers.get(container_name)
    except Exception as exc:
        return False, f"container not found: {exc}"

    # ------------------------------------------------------------------------
    # First determine whether root password already works.
    # ------------------------------------------------------------------------
    root_password_works = _mysql_ping_with_password(
        container,
        root_password,
    )

    # ------------------------------------------------------------------------
    # If root password does NOT work, try local socket without password.
    # ------------------------------------------------------------------------
    if not root_password_works:

        ok, output = _mysql_exec(
            container,
            "SELECT 1;",
        )

        if not ok:
            return False, (
                "Cannot authenticate to MySQL as root. "
                "The configured root password does not work and "
                "socket authentication without password also failed. "
                f"mysql output: {output[-1000:]}"
            )

        # --------------------------------------------------------------------
        # Root currently has no password / socket authentication.
        # Set it now with mysql_native_password.
        # --------------------------------------------------------------------
        root_q = _mysql_string(root_password)

        statements = [
            (
                "ALTER USER 'root'@'localhost' "
                "IDENTIFIED WITH mysql_native_password BY "
                f"'{root_q}'"
            ),
            (
                "CREATE USER IF NOT EXISTS 'root'@'%' "
                "IDENTIFIED WITH mysql_native_password BY "
                f"'{root_q}'"
            ),
            (
                "ALTER USER 'root'@'%' "
                "IDENTIFIED WITH mysql_native_password BY "
                f"'{root_q}'"
            ),
            (
                "GRANT ALL PRIVILEGES ON *.* "
                "TO 'root'@'%' WITH GRANT OPTION"
            ),
            "FLUSH PRIVILEGES",
        ]

        for statement in statements:
            ok, output = _mysql_exec(
                container,
                statement,
            )
            if not ok:
                return False, (
                    "Failed to initialize root credentials. "
                    f"SQL error: {output[-1000:]}"
                )

        # Verify
        if not _mysql_ping_with_password(
            container,
            root_password,
        ):
            return False, (
                "Root password was configured but verification failed."
            )

    else:

        # --------------------------------------------------------------------
        # Root password works, but we MUST force it to mysql_native_password
        # so the application user verification step doesn't fail later.
        # --------------------------------------------------------------------
        logger.info(
            "MySQL root credentials already valid for '%s'; "
            "forcing mysql_native_password and continuing with user/db reconciliation.",
            container_name,
        )

        root_q = _mysql_string(root_password)

        statements = [
            (
                "ALTER USER 'root'@'localhost' "
                "IDENTIFIED WITH mysql_native_password BY "
                f"'{root_q}'"
            ),
            (
                "CREATE USER IF NOT EXISTS 'root'@'%' "
                "IDENTIFIED WITH mysql_native_password BY "
                f"'{root_q}'"
            ),
            (
                "ALTER USER 'root'@'%' "
                "IDENTIFIED WITH mysql_native_password BY "
                f"'{root_q}'"
            ),
            (
                "GRANT ALL PRIVILEGES ON *.* "
                "TO 'root'@'%' WITH GRANT OPTION"
            ),
            "FLUSH PRIVILEGES",
        ]

        for statement in statements:
            ok, output = _mysql_exec(
                container,
                statement,
                password=root_password,
            )
            if not ok:
                return False, (
                    "Failed while synchronizing root@%. "
                    f"SQL error: {output[-1000:]}"
                )

    # =========================================================================
    # Application user
    # =========================================================================

    if username:

        if username.lower() == "root":
            return False, (
                "Application username 'root' is not allowed. "
                "Use a separate application user."
            )

        username_q = _mysql_string(username)
        password_q = _mysql_string(user_password)

        # --------------------------------------------------------------------
        # Create user if missing (with mysql_native_password).
        # --------------------------------------------------------------------
        # Create + password for both '%' (TCP from other containers)
        # and 'localhost' (Unix socket — used by our verification and
        # local tooling).  Without localhost the socket verify fails
        # even when the user is correctly set up for remote access.
        for host in ("%", "localhost"):
            create_user_sql = (
                f"CREATE USER IF NOT EXISTS "
                f"'{username_q}'@'{host}' "
                f"IDENTIFIED WITH mysql_native_password BY '{password_q}'"
            )
            ok, output = _mysql_exec(
                container,
                create_user_sql,
                password=root_password,
            )
            if not ok:
                return False, (
                    f"Failed to create MySQL user '{username}'@'{host}'. "
                    f"SQL error: {output[-1000:]}"
                )

            alter_user_sql = (
                f"ALTER USER "
                f"'{username_q}'@'{host}' "
                f"IDENTIFIED WITH mysql_native_password BY '{password_q}'"
            )
            ok, output = _mysql_exec(
                container,
                alter_user_sql,
                password=root_password,
            )
            if not ok:
                return False, (
                    f"Failed to update password for MySQL user "
                    f"'{username}'@'{host}'. "
                    f"SQL error: {output[-1000:]}"
                )

        # --------------------------------------------------------------------
        # Database
        # --------------------------------------------------------------------

        if database:

            database_q = _mysql_identifier(database)

            create_database_sql = (
                f"CREATE DATABASE IF NOT EXISTS `{database_q}`"
            )

            ok, output = _mysql_exec(
                container,
                create_database_sql,
                password=root_password,
            )

            if not ok:
                return False, (
                    f"Failed to create database '{database}'. "
                    f"SQL error: {output[-1000:]}"
                )

            # ----------------------------------------------------------------
            # Grant
            # ----------------------------------------------------------------

            for host in ("%", "localhost"):
                grant_sql = (
                    f"GRANT ALL PRIVILEGES "
                    f"ON `{database_q}`.* "
                    f"TO '{username_q}'@'{host}'"
                )
                ok, output = _mysql_exec(
                    container,
                    grant_sql,
                    password=root_password,
                )
                if not ok:
                    return False, (
                        f"Failed to grant database '{database}' "
                        f"to user '{username}'@'{host}'. "
                        f"SQL error: {output[-1000:]}"
                    )

        # --------------------------------------------------------------------
        # Flush
        # --------------------------------------------------------------------

        ok, output = _mysql_exec(
            container,
            "FLUSH PRIVILEGES",
            password=root_password,
        )

        if not ok:
            return False, (
                "Failed to flush MySQL privileges. "
                f"SQL error: {output[-1000:]}"
            )

    # =========================================================================
    # Final root verification
    # =========================================================================

    if not _mysql_ping_with_password(
        container,
        root_password,
    ):
        return False, (
            "Final root password verification failed."
        )

    # =========================================================================
    # Verify application user
    # =========================================================================

    if username:

        try:
            verify_sql = "SELECT CURRENT_USER();"
            env = {
                "MYSQL_PWD": user_password,
            }

            exit_code, output = container.exec_run(
                [
                    "mysql",
                    f"-u{username}",
                    "--protocol=socket",
                    "--batch",
                    "--skip-column-names",
                    "-e",
                    verify_sql,
                ],
                environment=env,
            )

            output_text = (
                output.decode(
                    "utf-8",
                    "replace",
                )
                if isinstance(output, bytes)
                else str(output or "")
            )

            if int(exit_code) != 0:
                return False, (
                    f"MySQL user '{username}' was configured but "
                    f"credential verification failed. "
                    f"SQL output: {output_text[-1000:]}"
                )

        except Exception as exc:
            return False, (
                f"MySQL application user verification failed: {exc}"
            )

    return True, (
        "MySQL credentials successfully reconciled. "
        "Root password, application user, database and privileges "
        "were applied and verified."
    )


# ============================================================================
# DB Deployer
# ============================================================================

class DBDeployer:

    def deploy(
        self,
        *,
        container_name: str,
        platform: str,
        cfg: dict[str, Any],
        event_sink=None,
        deployment_id: str | None = None,
        force_reinit: bool = False,
    ) -> DBDeployResult:

        from deployments.core.deployment_logger import DeploymentLogger

        log = DeploymentLogger(
            deployment_id=deployment_id,
            sink=event_sink,
        )

        # ====================================================================
        # 1. Validate
        # ====================================================================

        errors = validate_db_config(
            platform,
            cfg,
        )

        if errors:

            message = (
                "DB config validation failed: "
                + "; ".join(errors)
            )

            log.error(
                "validation",
                message,
                progress=100,
                details={"errors": errors},
            )

            return DBDeployResult(
                success=False,
                message=message,
                container_name=container_name,
                platform=platform,
                error=message,
                details={"errors": errors},
            )

        log.info(
            "validation",
            f"Config validated for '{platform}'.",
            progress=5,
        )

        # ====================================================================
        # 2. Image
        # ====================================================================

        base_image = _DB_IMAGES.get(platform)

        if not base_image:

            message = (
                f"Unsupported DB platform '{platform}'."
            )

            log.error(
                "image_pull",
                message,
                progress=100,
            )

            return DBDeployResult(
                success=False,
                message=message,
                container_name=container_name,
                platform=platform,
                error=message,
            )

        if base_image.startswith(
            (
                "ghcr.io",
                "mcr.",
                "quay.",
            )
        ):
            full_image = base_image
        else:
            full_image = (
                f"{MIRROR_DOCKER}/{base_image}"
            )

        # ====================================================================
        # 3. Docker client
        # ====================================================================

        try:

            client = Client()()

        except Exception as exc:

            message = (
                f"Failed to create Docker client: {exc}"
            )

            log.error(
                "docker_client",
                message,
                progress=100,
            )

            return DBDeployResult(
                success=False,
                message=message,
                container_name=container_name,
                platform=platform,
                error=str(exc),
            )

        # ====================================================================
        # 4. Pull image
        # ====================================================================

        log.info(
            "image_pull",
            f"Pulling image '{full_image}'.",
            progress=10,
        )

        try:

            repo, separator, tag = full_image.rpartition(":")

            if not separator:
                repo = full_image
                tag = "latest"

            client.images.pull(
                repo,
                tag=tag,
            )

        except (
            APIError,
            docker.errors.DockerException,
        ) as exc:

            message = (
                f"Failed to pull image '{full_image}': {exc}"
            )

            log.error(
                "image_pull",
                message,
                progress=100,
            )

            return DBDeployResult(
                success=False,
                message=message,
                container_name=container_name,
                platform=platform,
                error=str(exc),
            )

        log.info(
            "image_pull",
            f"Image '{full_image}' ready.",
            progress=25,
        )

        # ====================================================================
        # 5. Normalize MySQL credentials
        # ====================================================================

        if platform in (
            "mysql",
            "mariadb",
        ):

            cfg = dict(cfg)

            if not _clean(
                cfg.get("root_password")
            ):

                cfg["root_password"] = _clean(
                    cfg.get("password")
                )

        # ====================================================================
        # 6. Environment
        # ====================================================================

        try:

            environment = _ENV_BUILDERS[
                platform
            ](cfg)

        except DeploymentError as exc:

            message = getattr(
                exc,
                "message",
                str(exc),
            )

            log.error(
                "validation",
                message,
                progress=100,
            )

            return DBDeployResult(
                success=False,
                message=message,
                container_name=container_name,
                platform=platform,
                error=message,
            )

        # ====================================================================
        # Extra environment
        # ====================================================================

        protected_env_keys = {
            "MYSQL_ROOT_PASSWORD",
            "MYSQL_PASSWORD",
            "MYSQL_USER",
            "MYSQL_DATABASE",

            "MARIADB_ROOT_PASSWORD",
            "MARIADB_PASSWORD",
            "MARIADB_USER",
            "MARIADB_DATABASE",

            "POSTGRES_PASSWORD",
            "POSTGRES_USER",
            "POSTGRES_DB",

            "MONGO_INITDB_ROOT_USERNAME",
            "MONGO_INITDB_ROOT_PASSWORD",
            "MONGO_INITDB_DATABASE",

            "ORACLE_PASSWORD",
            "ORACLE_PWD",

            "REDIS_PASSWORD",

            "MYSQL_ALLOW_EMPTY_PASSWORD",
            "MYSQL_RANDOM_ROOT_PASSWORD",
            "MARIADB_ALLOW_EMPTY_PASSWORD",
        }

        extra_env = cfg.get("env") or {}

        if isinstance(extra_env, dict):

            for key, value in extra_env.items():

                key = str(key)

                if key.upper() in protected_env_keys:
                    continue

                environment[key] = str(value)

        # ====================================================================
        # Final MySQL safety
        # ====================================================================

        if platform in (
            "mysql",
            "mariadb",
        ):

            root_password = _clean(
                environment.get(
                    "MYSQL_ROOT_PASSWORD"
                )
                or environment.get(
                    "MARIADB_ROOT_PASSWORD"
                )
            )

            if not root_password:

                message = (
                    "Refusing to start MySQL/MariaDB because "
                    "root password is empty."
                )

                log.error(
                    "validation",
                    message,
                    progress=100,
                )

                return DBDeployResult(
                    success=False,
                    message=message,
                    container_name=container_name,
                    platform=platform,
                    error=message,
                )

            environment.pop(
                "MYSQL_ALLOW_EMPTY_PASSWORD",
                None,
            )

            environment.pop(
                "MYSQL_RANDOM_ROOT_PASSWORD",
                None,
            )

            environment.pop(
                "MARIADB_ALLOW_EMPTY_PASSWORD",
                None,
            )

        # ====================================================================
        # Redis command
        # ====================================================================

        command = None

        if platform == "redis":

            redis_password = _clean(
                cfg.get("password")
            )

            if redis_password:

                command = [
                    "redis-server",
                    "--requirepass",
                    redis_password,
                ]

        # ====================================================================
        # 7. Ports
        # ====================================================================

        container_port = _DEFAULT_PORTS.get(
            platform
        )

        publish_port = _safe_bool(
            cfg.get("publish_port")
        )

        host_port = None

        if publish_port and container_port:

            host_port = (
                cfg.get("port")
                or container_port
            )

        exposed_ports: dict[str, dict] = {}

        if container_port:

            exposed_ports = {
                f"{container_port}/tcp": {}
            }

        port_bindings: dict[str, list[dict]] = {}

        if (
            publish_port
            and container_port
            and host_port
        ):

            port_bindings = {
                f"{container_port}/tcp": [
                    {
                        "HostPort": str(
                            host_port
                        )
                    }
                ]
            }

        # ====================================================================
        # 8. Networks
        # ====================================================================

        networks: list[str] = []

        for network in cfg.get("networks") or []:

            if isinstance(network, str):

                name = network

            elif isinstance(network, dict):

                name = network.get("name")

            else:

                name = ""

            if name:

                networks.append(
                    str(name)
                )

        for network_name in networks:

            try:

                client.networks.get(
                    network_name
                )

            except NotFound:

                try:

                    client.networks.create(
                        network_name,
                        driver="bridge",
                    )

                except (
                    APIError,
                    docker.errors.DockerException,
                ) as exc:

                    logger.warning(
                        "Could not create network '%s': %s",
                        network_name,
                        exc,
                    )

        networking_config = None

        if networks:

            endpoints = {
                network_name:
                    client.api.create_endpoint_config()
                for network_name in networks
            }

            networking_config = (
                client.api.create_networking_config(
                    endpoints
                )
            )

        # ====================================================================
        # 9. Volumes
        # ====================================================================

        volume_binds: dict[str, dict] = {}

        for volume in cfg.get("volumes") or []:

            if not isinstance(volume, dict):
                continue

            source = (
                volume.get("source")
                or volume.get("name")
            )

            target = (
                volume.get("target")
                or volume.get("bind")
            )

            mode = volume.get(
                "mode",
                "rw",
            )

            if not source or not target:
                continue

            source = str(source)
            target = str(target)

            volume_binds[source] = {
                "bind": target,
                "mode": mode,
            }

            # Named volume
            if not source.startswith("/"):

                try:

                    client.volumes.get(
                        source
                    )

                except NotFound:

                    try:

                        client.volumes.create(
                            name=source
                        )

                    except (
                        APIError,
                        docker.errors.DockerException,
                    ) as exc:

                        logger.warning(
                            "Could not create volume '%s': %s",
                            source,
                            exc,
                        )

        # ====================================================================
        # 10. Remove old container FIRST
        # ====================================================================
        # MUST happen before force_reinit volume wipe.  Yanking a volume
        # from under a still-running container makes the container exit;
        # the monitor can then delete the replacement during readiness wait.

        log.info(
            "container_replacement",
            "Removing existing container if present.",
            progress=35,
        )

        try:

            old_container = client.containers.get(
                container_name
            )

            old_container.reload()

            if old_container.status == "running":

                old_container.stop(
                    timeout=10
                )

            old_container.remove(
                force=True
            )

        except NotFound:
            pass

        except (
            APIError,
            docker.errors.DockerException,
        ) as exc:

            message = (
                f"Failed to remove existing "
                f"container: {exc}"
            )

            log.error(
                "container_replacement",
                message,
                progress=100,
            )

            return DBDeployResult(
                success=False,
                message=message,
                container_name=container_name,
                platform=platform,
                error=str(exc),
            )

        # ====================================================================
        # 11. force_reinit (safe — no container holds the volume)
        # ====================================================================

        if force_reinit:

            for source in list(
                volume_binds.keys()
            ):

                if source.startswith("/"):
                    continue

                try:

                    volume = client.volumes.get(
                        source
                    )

                    volume.remove(
                        force=True
                    )

                    client.volumes.create(
                        name=source
                    )

                    log.info(
                        "volume_creation",
                        f"Recreated volume '{source}'.",
                        progress=30,
                    )

                except NotFound:
                    pass

                except (
                    APIError,
                    docker.errors.DockerException,
                ) as exc:

                    logger.warning(
                        "Could not reset volume '%s': %s",
                        source,
                        exc,
                    )

        # ====================================================================
        # 12. tmpfs
        # ====================================================================

        tmpfs = {
            "/tmp": (
                "rw,noexec,nosuid,size=64m"
            ),
            "/var/tmp": (
                "rw,noexec,nosuid,size=32m"
            ),
        }

        if platform in (
            "mysql",
            "mariadb",
        ):

            tmpfs[
                "/var/run/mysqld"
            ] = (
                "rw,noexec,nosuid,size=8m"
            )

        elif platform == "postgresql":

            tmpfs[
                "/var/run/postgresql"
            ] = (
                "rw,noexec,nosuid,size=8m"
            )

        # ====================================================================
        # 13. Host config
        # ====================================================================

        host_config_kwargs: dict[str, Any] = {
            "binds": volume_binds or None,
            "port_bindings": (
                port_bindings or None
            ),
            "read_only": False,
            "tmpfs": tmpfs,
            "init": True,
            "restart_policy": {
                "Name": "unless-stopped"
            },
        }

        max_cpu = cfg.get("max_cpu")

        if max_cpu is not None:

            try:

                cpu = float(max_cpu)

                if cpu > 0:

                    host_config_kwargs[
                        "nano_cpus"
                    ] = int(
                        cpu * 1_000_000_000
                    )

            except (
                TypeError,
                ValueError,
            ):
                pass

        max_ram = cfg.get("max_ram")

        if max_ram is not None:

            try:

                ram_mb = int(max_ram)

                if ram_mb > 0:

                    memory = (
                        ram_mb
                        * 1024
                        * 1024
                    )

                    host_config_kwargs[
                        "mem_limit"
                    ] = memory

                    host_config_kwargs[
                        "memswap_limit"
                    ] = memory

            except (
                TypeError,
                ValueError,
            ):
                pass

        # ====================================================================
        # Host config fallback
        # ====================================================================

        fallback_configs = [
            host_config_kwargs,

            {
                k: v
                for k, v in host_config_kwargs.items()
                if k != "memswap_limit"
            },

            {
                k: v
                for k, v in host_config_kwargs.items()
                if k not in {
                    "memswap_limit",
                    "nano_cpus",
                }
            },

            {
                k: v
                for k, v in host_config_kwargs.items()
                if k not in {
                    "memswap_limit",
                    "nano_cpus",
                    "mem_limit",
                }
            },

            {
                k: v
                for k, v in host_config_kwargs.items()
                if k not in {
                    "memswap_limit",
                    "nano_cpus",
                    "mem_limit",
                    "tmpfs",
                }
            },
        ]

        host_config = None
        last_error = None

        for candidate in fallback_configs:

            try:

                host_config = (
                    client.api.create_host_config(
                        **candidate
                    )
                )

                break

            except (
                TypeError,
                APIError,
                docker.errors.DockerException,
            ) as exc:

                last_error = exc

        if host_config is None:

            message = (
                "Failed to build Docker host config. "
                f"Last error: {last_error}"
            )

            log.error(
                "container_creation",
                message,
                progress=100,
            )

            return DBDeployResult(
                success=False,
                message=message,
                container_name=container_name,
                platform=platform,
                error=str(last_error),
            )

        # ====================================================================
        # 14. Create container
        # ====================================================================

        log.info(
            "container_creation",
            f"Creating '{container_name}'.",
            progress=60,
        )

        try:

            response = client.api.create_container(
                name=container_name,
                image=full_image,
                environment=environment,
                host_config=host_config,
                networking_config=networking_config,
                ports=(
                    list(exposed_ports.keys())
                    or None
                ),
                command=command,

                # Keep these for compatibility with MySQL versions that
                # exhibit daemon detection problems around stdin.
                tty=True,
                stdin_open=True,

                labels={
                    "managed-by":
                        "django-paas-deployer",
                    "platform":
                        platform,
                    "platform-type":
                        "DB",
                },
            )

            container_id = (
                response.get("Id")
                or response.get("id")
            )

            if not container_id:

                raise RuntimeError(
                    "Docker returned no container ID."
                )

        except (
            APIError,
            docker.errors.DockerException,
            RuntimeError,
        ) as exc:

            message = (
                f"Failed to create DB container: {exc}"
            )

            log.error(
                "container_creation",
                message,
                progress=100,
            )

            return DBDeployResult(
                success=False,
                message=message,
                container_name=container_name,
                platform=platform,
                error=str(exc),
            )

        # ====================================================================
        # 15. Start
        # ====================================================================

        log.info(
            "container_startup",
            "Starting database container.",
            progress=75,
        )

        try:

            client.api.start(
                container_id
            )

        except (
            APIError,
            docker.errors.DockerException,
        ) as exc:

            message = (
                f"Failed to start DB container: {exc}"
            )

            log.error(
                "container_startup",
                message,
                progress=100,
            )

            return DBDeployResult(
                success=False,
                message=message,
                container_name=container_name,
                platform=platform,
                error=str(exc),
            )

        # ====================================================================
        # 16. MySQL special handling
        # ====================================================================

        if platform in (
            "mysql",
            "mariadb",
        ):

            # Root password from the env we built (canonical).
            root_password = _clean(
                environment.get(
                    "MYSQL_ROOT_PASSWORD"
                )
                or environment.get(
                    "MARIADB_ROOT_PASSWORD"
                )
            )

            # App credentials ALWAYS from cfg — never from env.
            # We deliberately do not put MYSQL_USER/MYSQL_PASSWORD in env
            # so the entrypoint cannot create a half-configured user.
            # _reconcile_mysql_credentials owns all app-user / DB work.
            username = _clean(cfg.get("username"))
            user_password = (
                _clean(cfg.get("password"))
                or root_password
            )
            database = _clean(
                cfg.get("database")
                or environment.get("MYSQL_DATABASE")
                or environment.get("MARIADB_DATABASE")
            )

            # ----------------------------------------------------------------
            # Wait for real MySQL readiness
            # ----------------------------------------------------------------

            log.info(
                "health_check",
                "Waiting for MySQL server to become ready.",
                progress=85,
            )

            ready, ready_details = (
                _mysql_wait_until_ready(
                    client,
                    container_name,
                    timeout=180,
                    root_password=root_password,
                )
            )

            if not ready:

                log_tail = ""

                try:

                    container = client.containers.get(
                        container_name
                    )

                    raw = container.logs(
                        tail=100
                    )

                    log_tail = (
                        raw.decode(
                            "utf-8",
                            "replace",
                        )
                        if isinstance(raw, bytes)
                        else str(raw or "")
                    )

                except Exception:
                    pass

                message = (
                    "MySQL did not become ready within 180 seconds.\n\n"
                    f"Readiness details:\n{ready_details[-1500:]}\n\n"
                    f"Container logs:\n{log_tail[-3000:]}"
                )

                log.error(
                    "health_check",
                    message,
                    progress=100,
                )

                return DBDeployResult(
                    success=False,
                    message=message,
                    container_name=container_name,
                    platform=platform,
                    error=message,
                    details={
                        "logs": log_tail[-3000:],
                    },
                )

            # ----------------------------------------------------------------
            # THIS IS THE IMPORTANT PART
            #
            # We now reconcile credentials against the existing database.
            #
            # This works even if the volume already existed before this
            # deployment.
            # ----------------------------------------------------------------

            log.info(
                "credentials",
                "Reconciling MySQL credentials "
                "against existing database state.",
                progress=90,
            )

            ok, credential_message = (
                _reconcile_mysql_credentials(
                    client,
                    container_name,
                    root_password=root_password,
                    username=username,
                    user_password=user_password,
                    database=database,
                )
            )

            if not ok:

                message = (
                    "MySQL credential reconciliation failed: "
                    f"{credential_message}"
                )

                log.error(
                    "credentials",
                    message,
                    progress=100,
                )

                return DBDeployResult(
                    success=False,
                    message=message,
                    container_name=container_name,
                    platform=platform,
                    error=message,
                    details={
                        "credential_error":
                            credential_message,
                    },
                )

            log.info(
                "credentials",
                "MySQL credentials verified and synchronized.",
                progress=95,
            )

        # ====================================================================
        # 17. Other DB readiness
        # ====================================================================

        else:

            health_timeout = {
                "postgresql": 60,
                "mongodb": 60,
                "redis": 30,
                "oracle": 120,
            }.get(
                platform,
                60,
            )

            deadline = (
                time.monotonic()
                + health_timeout
            )

            running = False

            while time.monotonic() < deadline:

                try:

                    container = client.containers.get(
                        container_name
                    )

                    container.reload()

                    if container.status == "running":

                        running = True
                        break

                    if container.status in {
                        "dead",
                        "exited",
                    }:

                        break

                except Exception:
                    pass

                time.sleep(1)

            if not running:

                log_tail = ""

                try:

                    container = client.containers.get(
                        container_name
                    )

                    raw = container.logs(
                        tail=80
                    )

                    log_tail = (
                        raw.decode(
                            "utf-8",
                            "replace",
                        )
                        if isinstance(raw, bytes)
                        else str(raw or "")
                    )

                except Exception:
                    pass

                message = (
                    f"{platform} container did not become running.\n"
                    f"Logs:\n{log_tail[-3000:]}"
                )

                log.error(
                    "health_check",
                    message,
                    progress=100,
                )

                return DBDeployResult(
                    success=False,
                    message=message,
                    container_name=container_name,
                    platform=platform,
                    error=message,
                    details={
                        "logs": log_tail[-3000:],
                    },
                )

        # ====================================================================
        # 18. Final status
        # ====================================================================

        host_port_result = (
            int(host_port)
            if host_port
            else None
        )

        log.info(
            "deployment_completed",
            f"Database '{platform}' deployed successfully.",
            progress=100,
            details={
                "platform": platform,
                "image": full_image,
                "container_port": container_port,
                "host_port": host_port_result,
                "publish_port":
                    bool(host_port_result),
            },
        )

        return DBDeployResult(
            success=True,
            message=(
                f"Database '{platform}' deployed successfully."
            ),
            container_name=container_name,
            platform=platform,
            port=(
                host_port_result
                or container_port
            ),
            details={
                "image": full_image,
                "container_port": container_port,
                "host_port": host_port_result,
                "publish_port":
                    bool(host_port_result),
            },
        )

    # =========================================================================
    # Remove
    # =========================================================================

    def remove(
        self,
        container_name: str,
    ) -> bool:

        try:

            client = Client()()

            container = client.containers.get(
                container_name
            )

            container.reload()

            if container.status == "running":

                container.stop(
                    timeout=10
                )

            container.remove(
                force=True
            )

            logger.info(
                "DB container '%s' removed.",
                container_name,
            )

            return True

        except NotFound:

            return False

        except (
            APIError,
            docker.errors.DockerException,
        ) as exc:

            raise DeploymentError(
                f"Failed to remove DB container "
                f"'{container_name}'.",
                stage="container_removal",
                details={
                    "error": str(exc)
                },
            ) from exc