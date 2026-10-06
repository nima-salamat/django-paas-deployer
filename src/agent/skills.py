"""Discoverable, scope-aware Agent skills.

Skills are intentionally separate from AGENT.md. AGENT.md stays small and
stable; each skill is a focused operating playbook exposed at
/agent/v1/skills/<name>.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Skill:
    name: str
    title: str
    summary: str
    scopes: tuple[str, ...] = ()
    any_scopes: tuple[str, ...] = ()
    body: str = ""

    def enabled_for(self, selected: set[str]) -> bool:
        return set(self.scopes).issubset(selected) and (
            not self.any_scopes or bool(set(self.any_scopes) & selected)
        )


def _skill(
    name: str,
    title: str,
    summary: str,
    body: str,
    *,
    scopes: Iterable[str] = (),
    any_scopes: Iterable[str] = (),
) -> Skill:
    return Skill(
        name=name,
        title=title,
        summary=summary,
        scopes=tuple(scopes),
        any_scopes=tuple(any_scopes),
        body=body.strip(),
    )


SKILLS: tuple[Skill, ...] = (
    _skill(
        "services",
        "Services",
        "Inspect services and change service lifecycle state.",
        """
# Services

Use this skill for service discovery, inspection, lifecycle actions, and
service-level state. Prefer the first-class Service API over shell.

## Endpoints

- GET {{base}}/services
- GET/PATCH/DELETE {{base}}/services/{service_id}
- GET {{base}}/services/{service_id}/status
- GET {{base}}/services/{service_id}/metrics
- POST {{base}}/services/{service_id}/start
- POST {{base}}/services/{service_id}/stop
- POST {{base}}/services/{service_id}/restart
- POST {{base}}/services/{service_id}/rebuild
- POST {{base}}/services/{service_id}/purge-runtime

## First-class tools

- `php.lint` checks PHP syntax for one workspace file.
- `php.composer` provides constrained Composer actions (`validate`, `show`,
  `outdated`, `install`, `update`) when Composer is actually installed.

Call `/services/{service_id}/tools` and `/runtime.detect` before assuming
Composer exists in a runtime image.
## Rules

Use /capabilities to confirm the granted scope before mutating. Use OpenAPI for
exact fields. Do not modify server-owned fields or resource limits. Distinguish
desired service state from observed runtime state.

After lifecycle operations, inspect service/status and, when relevant, logs.
Rebuild and purge are operationally significant; never use shell to emulate
them.
        """,
        any_scopes=("services.read", "services.create", "services.update", "services.delete", "services.start", "services.stop", "services.restart", "services.purge"),
    ),
    _skill(
        "deployments",
        "Deployments",
        "Create, inspect, upload, start, cancel, redeploy, rebuild and roll back deployments.",
        """
# Deployments

Use this skill for deployment workflows. Read deployment help before building
non-trivial configuration.

## Endpoints

- GET {{base}}/deployments
- POST {{base}}/deployments
- GET {{base}}/deployments/help
- POST {{base}}/deployments/inspect
- GET {{base}}/deployments/{deployment_id}
- DELETE {{base}}/deployments/{deployment_id}
- POST {{base}}/deployments/{deployment_id}/upload
- POST {{base}}/deployments/{deployment_id}/start
- POST {{base}}/deployments/{deployment_id}/cancel
- POST {{base}}/deployments/{deployment_id}/redeploy
- POST {{base}}/deployments/{deployment_id}/rebuild
- POST {{base}}/deployments/{deployment_id}/rollback
- GET {{base}}/deployments/{deployment_id}/logs
- GET {{base}}/deployments/{deployment_id}/logs/export

## Workflow

For complex deployment work: read /capabilities, then
/deployments/help, then /openapi.json. Inspect ZIPs before upload when useful.
After starting, observe deployment state and logs; do not declare success just
because a request was accepted.

Deployment confirmation/scope requirements are authoritative. Never replace a
blocked deployment operation with an improvised shell mutation.
        """,
        any_scopes=("deployments.read", "deployments.create", "deployments.upload", "deployments.start", "deployments.cancel", "deployments.redeploy", "deployments.rebuild", "deployments.rollback", "deployments.delete", "deployments.logs.read", "deployments.logs.export"),
    ),
    _skill(
        "configuration",
        "Service Configuration",
        "Read and update desired source, build, runtime and desired-state configuration.",
        """
# Service Configuration

Use this skill for control-plane configuration. Do not use shell to edit
configuration that PassDeployer owns.

## Endpoints

- GET/PATCH {{base}}/services/{service_id}/configuration
- GET {{base}}/services/{service_id}/revisions
- GET {{base}}/services/{service_id}/revisions/{revision_id}
- POST {{base}}/services/{service_id}/revisions/{revision_id}/rollback

## Rules

Read the current configuration before patching when the change depends on
existing values. Send only fields permitted by OpenAPI. Treat source/build/
runtime configuration and desired_state as control-plane state.

After a configuration change, verify the resulting configuration and then
observe deployment/runtime state if reconciliation is expected.
        """,
        any_scopes=("service_config.read", "service_config.write"),
    ),
    _skill(
        "environment-secrets",
        "Environment and Secrets",
        "Manage environment variables and secret material through dedicated APIs.",
        """
# Environment and Secrets

Use dedicated resource APIs for environment variables and secrets. Do not
store secret values in normal configuration or expose them through shell output.

## Environment endpoints

- GET {{base}}/services/{service_id}/environment
- POST {{base}}/services/{service_id}/environment
- DELETE {{base}}/services/{service_id}/environment?key={name}

## Secret endpoints

- GET {{base}}/services/{service_id}/secrets
- POST {{base}}/services/{service_id}/secrets
- DELETE {{base}}/services/{service_id}/secrets?key={name}

## Rules

Use OpenAPI for exact request fields. Normal secret reads return metadata, not
plaintext. Treat any revealed secret or credential response as sensitive and
never place it in logs, shell commands, or user-visible output.
        """,
        any_scopes=("service_environment.read", "service_environment.write", "service_secrets.read", "service_secrets.write"),
    ),
    _skill(
        "networking-databases",
        "Networking and Databases",
        "Manage private networks, service attachments, database bindings and database credentials.",
        """
# Networking and Databases

Use the dedicated control-plane APIs for network and database resources.

## Network endpoints

- GET/POST {{base}}/networks
- GET/PATCH/DELETE {{base}}/networks/{network_id}
- GET {{base}}/services/{service_id}/networks
- POST/DELETE {{base}}/services/{service_id}/networks

## Database endpoints

- GET {{base}}/services/{service_id}/databases
- POST/DELETE {{base}}/services/{service_id}/databases
- GET {{base}}/services/{service_id}/database-credentials

## Rules

Do not configure databases or networks by hand through container shell when a
first-class endpoint exists. Use the service/network/database identifiers
returned by the API. Credential revelation, where supported, needs the
dedicated high-risk scope and must remain secret.
        """,
        any_scopes=(
            "service_networks.read",
            "service_networks.write",
            "service_config.read",
            "service_config.write",
            "service_database_credentials.read",
        ),
    ),
    _skill(
        "plans",
        "Plans",
        "Discover and apply plans and, where authorized, manage plan definitions.",
        """
# Plans

Use this skill for plan selection and plan lifecycle.

## Endpoints

- GET {{base}}/plans
- GET {{base}}/plans/{plan_id}
- POST {{base}}/plans/{plan_id}/apply
- POST {{base}}/plans/manage
- PATCH {{base}}/plans/manage/{plan_id}
- DELETE {{base}}/plans/manage/{plan_id}

## Rules

A plan defines server-owned resource limits and defaults. Do not inject tenant
CPU/RAM/worker overrides into Service creation when the plan owns them.

Use /openapi.json for the exact writable fields and idempotency contract. After
applying a plan, inspect the resulting service rather than assuming the plan
was fully applied.
        """,
        any_scopes=("plans.read", "plans.manage", "plans.apply"),
    ),
    _skill(
        "observability",
        "Logs and Observability",
        "Read runtime logs, deployment logs and runtime metrics.",
        """
# Logs and Observability

Use dedicated observability APIs before shell whenever the requested information
is already represented there.

## Runtime endpoints

- GET {{base}}/services/{service_id}/logs
- GET {{base}}/services/{service_id}/logs/export
- GET {{base}}/services/{service_id}/metrics

## Deployment endpoints

- GET {{base}}/deployments/{deployment_id}/logs
- GET {{base}}/deployments/{deployment_id}/logs/export

Runtime logs and deployment logs are separate sources. Use deployment logs for
lifecycle/build events and runtime logs for the running service. Respect the
documented pagination/cursor fields and preserve request ids when diagnosing
errors.
        """,
        any_scopes=("service_logs.read", "service_logs.export", "deployments.logs.read", "deployments.logs.export"),
    ),
    _skill(
        "endpoints",
        "Service Endpoints",
        "Manage service ports, hostnames, paths, exposure and endpoint configuration.",
        """
# Service Endpoints

Use this skill for service ingress/exposure configuration. Prefer the endpoint
resource API over shell or web-server edits.

## Endpoints

- GET {{base}}/services/{service_id}/endpoints
- POST {{base}}/services/{service_id}/endpoints
- DELETE {{base}}/services/{service_id}/endpoints?name={name}

## Rules

Read the current endpoints before making dependent changes. Use OpenAPI for the
exact fields and enums for target_port, published_port, protocol, exposure,
process, hostname, path, tls and enabled. Ports are server-validated.

Treat platform-managed hostnames and other server-owned fields as authoritative.
After a mutation, read the endpoint configuration back and verify any resulting
service/deployment state.
        """,
        any_scopes=("service_endpoints.read", "service_endpoints.write"),
    ),
    _skill(
        "volumes",
        "Volumes",
        "Manage service volumes and inspect their bindings and lifecycle state.",
        """
# Volumes

Use this skill for persistent storage resources. Do not emulate volume
configuration by mounting paths manually from inside the runtime shell.

## Endpoints

- GET/POST {{base}}/volumes
- GET/PATCH/DELETE {{base}}/volumes/{volume_id}

## Rules

Use the volume API for resource creation and lifecycle changes. Respect plan,
quota and server-owned volume constraints. Use the returned volume id and
binding metadata when connecting storage to a service.

A runtime path being writable does not imply a volume exists, and a volume
being attached does not imply every path under it is writable by the service
process UID. Verify the actual resource and runtime state after important
storage changes.
        """,
        any_scopes=("service_volumes.read", "service_volumes.write"),
    ),
    _skill(
        "php",
        "PHP Runtime",
        "Develop and diagnose PHP applications inside the service workspace.",
        """
# PHP Runtime

Use this skill for PHP services and PHP-based application development.

## Workspace

For PHP web runtimes the managed workspace is normally `/var/www/html`.
Always call `GET {{base}}/services/{service_id}/shell` before opening a session
and use the returned `workspace.default_workdir` rather than assuming a path.

## Commands

Use the restricted shell command catalog for PHP and Composer. Direct
`php -r`, arbitrary PHP script execution, and unrestricted shell interpreters
are blocked by policy. Use application/framework CLIs when they exist.

For file changes use `POST {{base}}/services/{service_id}/shell/files` rather than
building shell pipelines. Re-read changed files and inspect runtime logs after
important mutations.

## Rules

Do not modify platform-owned configuration through the runtime when a
PassDeployer configuration endpoint owns it. Never put credentials in command
arguments or generated files.
        """,
        scopes=("shell.read", "shell.execute", "shell.files.read", "shell.files.write"),
    ),
    _skill(
        "wordpress",
        "WordPress",
        "Operate a WordPress runtime, including themes, plugins, PHP/CSS/JS files and runtime diagnosis.",
        """
# WordPress

Use this skill for a WordPress service running in the managed container.

## Workspace

The canonical WordPress document root is `/var/www/html`. Confirm it from
`GET {{base}}/services/{service_id}/shell` before acting.

Typical site code is under:
- `/var/www/html/wp-content/themes`
- `/var/www/html/wp-content/plugins`
- `/var/www/html/wp-content/uploads`

Never delete `wp-config.php`, the WordPress database volume, or the WordPress
persistent volume merely to fix a code/configuration issue.

## Tool-first workflow

1. Call /services/{service_id}/tools and inspect the available WordPress tools.
2. Use runtime.detect when unsure whether an optional CLI is present.
3. Prefer wordpress.wp_cli for supported CMS operations instead of inventing SQL.
4. Use php.lint after changing PHP.

## Workflow

1. Inspect service status, shell metadata and runtime logs.
2. Inspect `wp-content` before editing anything.
3. Prefer the managed workspace file API for edits and verify each important write.
4. This Ready App image includes WP-CLI 2.12.0 on PATH. Use `wp --info` or
   `wp cli version` for a cheap runtime verification before CMS mutations.
5. Use the interactive PTY for commands that need a persistent stdin session.
6. After changes, verify PHP/Apache logs and request the affected public URL.
7. Use a PassDeployer deployment/rebuild operation only when the change belongs
   to the immutable deployment/runtime configuration rather than persistent
   WordPress content.

## First-class tools

Prefer these Agent tools when they are available:
- `wordpress.inspect` for a structured site snapshot before making changes.
- `wordpress.page.create` for creating Pages without manually building WP-CLI arguments.
- `wordpress.plugin.manage` and `wordpress.theme.manage` for plugin/theme lifecycle operations.
- `wordpress.cache.flush` after cache-sensitive changes.
- `wordpress.wp_cli` for other supported non-interactive WP-CLI operations.

The tool list is runtime- and scope-filtered. Do not assume a tool is enabled
only because it is documented; call `/services/{service_id}/tools` first.
## Content vs code

Theme/plugin PHP, CSS and JavaScript changes belong in the workspace.
WordPress Pages, Posts, menus, users, plugin activation, theme activation and
most site settings are database-backed CMS state; do not fake them by editing
random files.

Prefer WP-CLI for CMS operations. Common patterns include:
- `wp core version` and `wp core verify-checksums` for diagnostics
- `wp theme list`, `wp theme activate <slug>` (activation is privileged)
- `wp plugin list`, `wp plugin install <slug>`; activation is a separate privileged operation
- `wp post create`, `wp post update`, `wp page create`
- `wp option get/set`, `wp menu list`
- `wp user list/create/update`
- `wp rewrite flush`, `wp cache flush`
- `wp search-replace` for controlled URL/content migrations
- `wp db cli` for an interactive database session

The shell policy blocks WP-CLI code-loading commands such as `wp eval`,
`wp eval-file`, `wp shell`, and global `--require/--exec` options. Use the
managed file API for source files and WP-CLI for CMS state.

## Safety

Preserve existing themes, plugins and content. Do not overwrite `wp-config.php`
with ad-hoc HTTPS/PHP bootstrap code. Platform HTTPS is already represented by
the runtime reverse-proxy contract.
        """,
        scopes=("shell.read", "shell.execute", "shell.files.read", "shell.files.write"),
    ),
    _skill(
        "databases",
        "Databases",
        "Operate managed MySQL, MariaDB, PostgreSQL, MongoDB, Redis and Oracle runtimes with engine-aware shells.",
        """
# Databases

Use this skill for database-provider services.

## Supported engines

MySQL, MariaDB, PostgreSQL, MongoDB, Redis and Oracle are recognized as
database runtimes by the shell.

## Tool-first workflow

1. Call `/services/{service_id}/tools`.
2. Call `runtime.detect` for client binaries.
3. Call `workspace.inspect` when storage or permissions matter.
4. Use `database.health` for non-destructive readiness checks.
5. Use the database PTY for actual SQL/commands that require an interactive client.
## Workspace

Restricted database sessions use a safe workspace (normally `/tmp`) and must not edit the engine data directory directly. Developer sessions use the image-native runtime working directory while retaining the container security boundary.
- MySQL / MariaDB runtime cwd: `/` · data root: `/var/lib/mysql`
- PostgreSQL runtime cwd: `/` · data root: `/var/lib/postgresql/data`
- MongoDB runtime cwd: `/` · data root: `/data/db`
- Redis runtime cwd: `/data` · data root: `/data`
- Oracle runtime cwd: `/opt/oracle` · data root: `/opt/oracle/oradata`

Always read `GET {{base}}/services/{service_id}/shell` first. It reports the
resolved engine, safe workspace root, data root and interactive commands.

## Interactive clients

Interactive database clients require the service’s advanced-shell permission. For Agent developer mode, the additional `shell.developer` scope is required; restricted database PTY access uses the normal advanced-interactive permission. Low-privilege shared users do not automatically receive database PTY access.

Use the PTY/WebSocket transport for:
- `mysql -u<username>` for MySQL (or `-uroot` when no managed username is reported)
- `mariadb -u<username>` for MariaDB (or `-uroot` when no managed username is reported)
- `psql`
- `pg_isready` for PostgreSQL readiness checks
- `mongosh --host 127.0.0.1 --username <username> --authenticationDatabase admin` for authenticated MongoDB
- `redis-cli`
- `sqlplus /nolog` for Oracle SQL*Plus

The platform injects managed credentials into the supported local client
environment where the client supports it. For MySQL/MariaDB, use the username
reported by `workspace.database.username`; the command catalog is generated
with that username when one exists. For PostgreSQL, `PGUSER`, `PGPASSWORD`,
`PGDATABASE`, and local `PGHOST`/`PGPORT` are supplied to the PTY. Never put passwords in command-line
arguments, URLs, SQL strings, shell history or audit messages.

## Access and storage reality

The database data directory is storage, not an application source tree. Do not
expect to edit database files directly. Use the engine client for logical data
operations.

The database may be attached to a volume, but the volume can be mounted
read-only or the runtime user may lack write permission. Use workspace.inspect
before path-based work and treat its result as authoritative for the runtime
view.

## Rules

Database batch flags such as `-e`, `--execute`, `-c`, `-f` and `--eval` are
intentionally blocked in the restricted command API. Use the interactive PTY
for actual SQL/queries so the transport and engine session remain explicit.

Keep client connections local to the managed database runtime. Do not use the
database shell as a general network client or to pivot to another host.

For destructive schema/data changes, inspect the target first and obtain the
user's explicit confirmation before executing the mutation. Verify the result
afterward.

Use the control-plane database binding/credential APIs for service bindings;
do not recreate those relationships from inside a database container.

## Agent interactive transport

The HTTP `POST .../shell/sessions/{session_id}/commands` endpoint is for one-shot
commands. Interactive database clients require the persistent PTY WebSocket.

After creating a shell session, construct the WebSocket URL from the Agent API
origin by replacing `https://` with `wss://` and using the `interactive_pty.websocket_path`
returned by the shell metadata endpoint. Authenticate the WebSocket with:
- `agent_token=<agent access token>`
- `shell_token=<temporary shell session token>`

Once connected, send `{ "type": "command", "command": "psql" }` (or the appropriate
engine client), then send `{ "type": "stdin", "data": "..." }` for responses and
queries. Use the `signal` message for Ctrl-C/Ctrl-D/Ctrl-Z/Ctrl-L and wait for
`process.exit` before starting another command.

The agent token is accepted only for the interactive shell transport and is
revalidated on connection and ping. Use TLS (`wss://`) and never place database
passwords in the command string.
For MongoDB and Oracle, no generic password environment variable is assumed.
When authentication is required, use the dedicated high-risk credential
endpoint only when authorized, start the interactive client, and provide
the password through PTY stdin. Never echo or log the password.

## Safe diagnostics

For MySQL/MariaDB use the engine-specific admin ping command from the command catalog. For PostgreSQL use `pg_isready`. These are read-only checks and do not require entering a SQL REPL.        """,
        scopes=("shell.read", "shell.execute"),
    ),
    _skill(
        "developer-shell",
        "Developer Shell",
        "Use a hardened interactive developer shell when the service and Agent explicitly grant developer-shell access.",
        """
# Developer Shell

Use this skill only when the Agent has the `shell.developer` scope and the
service grants advanced shell access.

## Mode

Create the session with:

`POST {{base}}/services/{service_id}/shell/sessions`

using `{"mode": "developer"}`.

Developer mode must use the interactive PTY/WebSocket transport. The normal
one-shot command endpoint intentionally does not execute developer-mode
commands.

## What it provides

Commands are executed by a real POSIX shell inside the service container, so
normal shell syntax, pipelines, redirects, scripts, environment changes within
the command, package managers and runtime CLIs work without PassDeployer
maintaining an allowlist of every possible command.

`cd` is persisted by PassDeployer for simple `cd <path>` commands. Other shell
state such as exported variables or aliases exists only for the child shell
that ran the command.

## Security boundary

Developer mode is not host shell access. PassDeployer refuses developer mode
for containers with privileged mode, host PID/network namespaces, Docker engine
socket/host Docker mounts, exposed host devices, dangerous added capabilities,
or an unconfined seccomp profile.

Do not assume developer mode can cross service-control-plane boundaries. Use the
dedicated Service, Deployment, Network, Volume, Secret and Database APIs for
managed resources.

Do not expect managed database passwords to be injected into developer shell
environments. Use the interactive database client and enter credentials through
its PTY prompt when required.
        """,
        scopes=("shell.read", "shell.execute", "shell.developer"),
    ),
    _skill(
        "runtime-tools",
        "Runtime Tools",
        "Discover and use first-class platform-aware runtime tools before falling back to low-level shell commands.",
        """
# Runtime Tools

The Agent has a tool layer in addition to the generic Service, Shell and file
APIs.

## Discovery

- GET {{base}}/services/{service_id}/tools
- POST {{base}}/services/{service_id}/tools/{tool_name}

The GET response is scope-filtered and platform-aware. Do not assume a tool is
available just because its name appears in documentation.

## Recommended workflow

1. Read /capabilities and /services/{service_id}/shell.
2. Read /services/{service_id}/tools.
3. Call workspace.inspect before editing paths whose storage/permissions are
   unclear.
4. Call runtime.detect when a framework CLI may or may not be installed.
5. Prefer a first-class platform tool over a raw shell command when both can
   perform the same task.
6. Use the interactive PTY for tools that explicitly report interactive
   transport requirements.

## Storage and access

A service can have several different storage layers:
- immutable image files
- persistent Docker volumes
- writable tmpfs or ephemeral paths
- control-plane configuration outside the runtime workspace

A path can exist without being writable. A Docker volume can be RW while the
runtime UID cannot write the target. Conversely, the managed file API can have
backend privileges that differ from the service UID.

When a path is outside the restricted workspace, treat that as a boundary, not
as a transient command failure. Ask the tool/API layer what operation owns that
resource instead of repeatedly trying filesystem commands.

## First-class platform tools

WordPress currently exposes:
- `wordpress.inspect`
- `wordpress.page.create`
- `wordpress.plugin.manage`
- `wordpress.theme.manage`
- `wordpress.cache.flush`
- `wordpress.wp_cli`

PHP-compatible services expose `php.lint` and `php.composer`.
Database runtimes expose `database.health` plus engine-specific interactive
clients through the Shell/PTTY transport.

These tools intentionally provide structured inputs. Prefer them to assembling
raw shell strings because the backend can validate their arguments and classify
the resulting mutation consistently.

## Platform examples
WordPress exposes structured policy-checked tools, while raw `wordpress.wp_cli`
is intentionally elevated and requires the `shell.developer` scope.
PHP/Laravel services expose PHP linting and their framework-aware Shell catalog.
Database services expose engine-aware Shell metadata and interactive clients.

Tool responses may report that a tool is not installed, not applicable, or
requires interactive PTY transport. Handle those outcomes explicitly.
        """,
        any_scopes=("shell.read", "shell.execute"),
    ),
    _skill(
        "python",
        "Python Runtime",
        "Develop, inspect and diagnose Python services inside the managed workspace.",
        """
# Python Runtime

Use this skill for Python services, including Flask/FastAPI runtimes.

## Workspace

Use GET {{base}}/services/{service_id}/shell first and use
workspace.default_workdir. Most application runtimes use /app, but the actual
service contract is authoritative.

Prefer the managed workspace file API for source changes. Use runtime.detect to
check Python, pip and optional tools before assuming they exist.

For framework-specific checks:
- Django: use python manage.py check, migrate and the documented management
  commands when available.
- FastAPI/Flask: inspect the actual application entrypoint and process command
  before changing it.

Do not assume a package is installed because it is present in requirements or
pyproject.toml. Verify the live container.

## Access

A path may exist in the image but not be writable because the root filesystem
or mount is read-only. A RW volume does not guarantee runtime-user write access.
Use workspace.inspect for uncertain paths.

Never put secrets into source files or shell command arguments.
        """,
        scopes=("shell.read", "shell.execute", "shell.files.read", "shell.files.write"),
    ),
    _skill(
        "node",
        "Node.js Runtime",
        "Develop and diagnose Node.js services and frontend build runtimes.",
        """
# Node.js Runtime

Use this skill for Node.js, React, Vue, Angular, Next.js and related build
services.

## Workspace

Read GET {{base}}/services/{service_id}/shell before starting. Use the returned
workspace.default_workdir rather than assuming /app.

Use runtime.detect to verify node, npm, npx, yarn, pnpm or bun availability.

## Workflow

Inspect package.json and lockfiles before changing dependencies. Prefer the
managed file API for source edits. Run the project's actual lint/test/build
scripts only after reading package scripts.

Package-manager commands can mutate the dependency tree. Inspect the diff and
verify the build result afterward.

Do not assume node_modules is persistent. It may be created in the image during
build and absent from a runtime-only filesystem.

## Storage

A build artifact directory can be image-backed while application data is
volume-backed. Use workspace.inspect when the task depends on persistence or
write access.

Never store credentials in package scripts, committed files or command history.
        """,
        scopes=("shell.read", "shell.execute", "shell.files.read", "shell.files.write"),
    ),
    _skill(
        "shell",
        "Restricted Runtime Shell",
        "Run authorized non-interactive or interactive commands inside a service runtime.",
        """
# Restricted Runtime Shell

Shell is a service-runtime facility, not host access.

## Endpoints

- GET {{base}}/services/{service_id}/shell
- POST {{base}}/services/{service_id}/shell/sessions
- POST {{base}}/services/{service_id}/shell/sessions/{session_id}/commands
- POST {{base}}/services/{service_id}/shell/sessions/{session_id}/close
- POST {{base}}/services/{service_id}/shell/replace

## Runtime tools and workspace reality

Use `GET {{base}}/services/{service_id}/tools` before complex runtime work. It
returns first-class tools that may be easier and safer than composing raw shell
commands.

Use `workspace.inspect` to learn whether the target path is inside the
managed workspace, backed by a Docker volume, mounted read-only, or writable
for the runtime user. A Docker RW mount does not guarantee that the service
UID can write to a path. The managed file API may have different permissions
from the runtime user.

If a requested path is outside the restricted workspace, do not keep retrying
the same command. Switch to a first-class control-plane API, workspace-file
operation, or developer shell only when the service security posture and
permission allow it.

## Storage access reality

Before changing an unfamiliar path, use `workspace.inspect` with that path.
The result distinguishes:
- image-backed files
- persistent Docker-volume mounts
- read-only mounts/root filesystem
- paths that are outside the restricted workspace
- paths where the Docker mount is RW but the runtime UID still cannot write.

A failed write does not automatically mean the file is absent, and a file being
present does not imply it is persistent. Use the mount metadata and live probe
before deciding whether the fix belongs in the image/build, a persistent volume,
or the PassDeployer control plane.

## Operating procedure

1. Read /services/{service_id}/shell, /services/{service_id}/tools and /capabilities.
2. Choose one-shot or PTY/WebSocket transport according to the returned policy.
3. Create a session and use its temporary shell token.
4. For ambiguous or compound commands, use dry_run when supported.
5. Inspect structured errors before retrying.
6. Inspect exit_code/stdout/stderr and verify important mutations.

Do not assume shell UID permissions equal managed file-manager permissions. Do not
use shell for a first-class control-plane or workspace file operation. Do not
set confirmation flags merely to force a blocked command. Interactive commands
must use the interactive transport when required.

## Agent interactive PTY

Interactive commands cannot be completed through the one-shot command endpoint.
Create a shell session first, then use the WebSocket path returned by
`GET {{base}}/services/{service_id}/shell`.

For an Agent connection use WSS with:
- `agent_token=<agent access token>`
- `shell_token=<temporary shell session token>`

Send one command message at a time. Use stdin messages for prompts and handle
`process.started`, `process.output`, `process.exit`, `confirm_required` and `error` events.
Use signal messages for Ctrl-C/Ctrl-D/Ctrl-Z/Ctrl-L.

The Agent token is validated on WebSocket connect and ping. Never put database
passwords or other secrets in command arguments.        """,
        scopes=("shell.read", "shell.execute"),
    ),
    _skill(
        "workspace-files",
        "Workspace Files",
        "Read and mutate files inside the authorized service workspace.",
        """
# Workspace Files

Use this skill whenever the task is fundamentally a file operation.

## Endpoint

- POST {{base}}/services/{service_id}/shell/files

Supported actions are discovered from OpenAPI and currently include read, write,
create, create_folder, rename, delete and upload.

## Rules

1. Check /capabilities for shell.files.read/write.
2. Read the OpenAPI request schema before sending the operation.
3. Keep paths inside the authorized service workspace.
4. Prefer the managed file API over shell pipelines.
5. Use the API's writable/mount metadata as the authority for supported writes.
6. Verify important writes by reading the target back.

The managed file operation may use backend-owned filesystem privileges that are
different from the service process UID. Therefore a path that looks writable
or read-only from one perspective is not by itself proof of the final API
permission result.

Never use this endpoint to modify platform-owned control-plane configuration
when a dedicated configuration endpoint exists.
        """,
        any_scopes=("shell.files.read", "shell.files.write"),
    ),
)


def all_skills() -> tuple[Skill, ...]:
    return SKILLS


def skill_for_agent(name: str, agent) -> Skill | None:
    skill = next((item for item in SKILLS if item.name == str(name)), None)
    if skill is None:
        return None
    return skill if skill.enabled_for(set(agent.scopes or [])) else None


def skills_for_agent(agent) -> list[Skill]:
    selected = set(agent.scopes or [])
    return [skill for skill in SKILLS if skill.enabled_for(selected)]


def skill_url(base_url: str, skill: Skill) -> str:
    return f"{base_url.rstrip('/')}/skills/{skill.name}"
