# PassDeployer Agent

## Identity

- Agent ID: {{ agent_id }}
- API version: v1
- API base URL: {{ api_base_url }}

This file is generated for this specific Agent. The operation list below is derived
from the same contract registry used by runtime scope enforcement and OpenAPI.

## Authentication and enrollment

PASSDEPLOYER_ENROLLMENT_TOKEN="{{ enrollment_token }}"

Exchange it exactly once:

    POST {{ api_base_url }}/auth/exchange
    {"enrollment_token":"$PASSDEPLOYER_ENROLLMENT_TOKEN"}

The exchange invalidates the enrollment credential and returns a normal Bearer
access token. Store the permanent access token only in a secure external secret
store. Never put a permanent token in a URL, repository, source file, or log.

## Issued scopes

{% for scope in scopes %}- `{{ scope }}`
{% empty %}- No operational scopes are enabled.
{% endfor %}

## Enabled API operations

Only operations that satisfy this Agent's issued scopes are listed.

| Method | Endpoint | Required scope(s) | Mutating | Idempotent | Throttle |
| --- | --- | --- | --- | --- | --- |
{% for endpoint in endpoints -%}
| `{{ endpoint.method }}` | `{{ endpoint.path }}` | `{{ endpoint.requirements }}` | {{ endpoint.mutating|yesno:"yes,no" }} | {{ endpoint.idempotent|yesno:"yes,no" }} | `{{ endpoint.throttle }}` |
{% empty -%}
| — | — | none | no | no | — |
{% endfor %}

## Discovery

Machine-readable capabilities:

    GET {{ api_base_url }}/capabilities

OpenAPI:

    GET {{ api_base_url }}/openapi.json

Complete deployment/configuration help:

    GET {{ api_base_url }}/deployments/help

ZIP inspection before creating a deployment:

    POST {{ api_base_url }}/deployments/inspect

Runtime metrics for an accessible service:

    GET {{ api_base_url }}/services/{service_id}/metrics

Database credentials are a separately scoped operation. A normal service read
never returns database passwords. When the Agent has the high-risk
`service_database_credentials.read` scope and the existing ServiceShare
policy allows `can_view_db_credentials`, use:

    GET {{ api_base_url }}/services/{service_id}/database-credentials?reveal=true

The response may contain a decrypted password/root password. Treat it as
secret material and never log or persist it.

## Operational rules

- Agent scopes are an upper bound. Existing PassDeployer User authorization and
  ServiceShare permissions remain authoritative.
- Deployment lifecycle logs and runtime service logs are separate sources.
- Revisions are immutable; rollback creates a new deployment through the
  existing rollback boundary.
- Secret values are never returned as normal API metadata. Use secret resources
  rather than placing sensitive values in ordinary configuration.
- Shell access remains inside the authorized service runtime/container. The
  host shell, Docker socket, and raw Docker API are not part of this contract.
- Restricted shell rules, path confinement, session TTLs, output limits and
  destructive-command confirmation remain enforced by the underlying shell
  subsystem.
- Send an `Idempotency-Key` on operations marked idempotent. Keys are scoped
  to this Agent and to the complete request shape.
- Re-check `/capabilities` when building an automation because the issued
  scopes can differ between Agents.
- Supported first-class deployment inputs are archive/ZIP and database-native
  deployment. Git and existing-image deployment are not part of this contract.
- CPU/RAM/PIDs/worker counts are server/Plan-controlled; never try to inject
  resource_limits, resources or worker-count overrides into tenant config.
- Volumes and networks are managed through their dedicated Agent endpoints so
  quota, ownership, attachment and lifecycle rules remain enforced.

## Common workflows

### Create from a plan

Use the plan-application operation only when both `services.create` and
`plans.apply` are issued.

### Deploy an archive

1. Create deployment metadata.
2. Upload the ZIP archive.
3. Start the deployment.
4. Poll deployment status.
5. Read deployment lifecycle logs when the logs scope is enabled.

### Diagnose a failure

Use deployment logs for lifecycle/build/orchestration events and runtime logs
for application/container output. Do not merge the two streams.

### Shell

The shell is intentionally a restricted service-container terminal, not a host
shell and not an unrestricted Bash interpreter.

There are two transports:

1. **One-shot command API**
   - Send one request to the shell command endpoint with a `command` string.
   - Safe compound commands are supported with `|`, `&&`, `||`, and `;`.
   - A sequence may contain at most 16 command segments.
   - Redirection, background execution and command substitution are rejected:
     `<`, `>`, `<<`, `<<<`, `&`, `&>`, `$()`, and backticks.
   - Pipeline input is bounded to 256 KiB.
   - Interactive commands are rejected here with `INTERACTIVE_REQUIRES_PTY`.

2. **Interactive PTY WebSocket**
   - Create a restricted shell session first.
   - Connect to `/ws/services/shell/{service_id}/`.
   - The PTY keeps the child process alive and supports stdin, Ctrl-C, Ctrl-D,
     Ctrl-Z and terminal resize messages.
   - Each top-level `command` message starts one validated process; compound
     shell syntax is deliberately disabled in this transport.

Use the PTY transport for commands that need a live prompt or REPL, for example:

- `php artisan tinker` / `php artisan psysh`
- `python manage.py shell` / `python manage.py shell_plus`
- `python manage.py createsuperuser`
- `python manage.py changepassword`

`tinker` is the Laravel interactive REPL (not "tkinter"). It is available only
when the underlying User/Service authorization allows advanced shell access.

For multi-step non-interactive work, use a safe compound command such as
`cd app && php artisan migrate && php artisan optimize`.

Do not infer support for arbitrary shell syntax from the command catalog. The
catalog is a list of suggestions; the runtime validator is the security boundary.
Destructive operations still require explicit confirmation.
## Error handling

Structured errors may include `code`, `detail`, `request_id`, `retryable`,
`failure_domain`, `visibility`, `resource_effect`, and `certainty`.
Treat permission failures, conflicts, invalid requests, transient failures,
confirmation requirements and unsupported capabilities as different conditions.
