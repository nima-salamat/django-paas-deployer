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

## Operating procedure

1. Read /services/{service_id}/shell and /capabilities.
2. Choose one-shot or PTY/WebSocket transport according to the returned policy.
3. Create a session and use its temporary shell token.
4. For ambiguous or compound commands, use dry_run when supported.
5. Inspect structured errors before retrying.
6. Inspect exit_code/stdout/stderr and verify important mutations.

Do not assume shell UID permissions equal managed file-manager permissions. Do not
use shell for a first-class control-plane or workspace file operation. Do not
set confirmation flags merely to force a blocked command. Interactive commands
must use the interactive transport when required.
        """,
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
